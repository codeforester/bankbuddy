"""Statement import helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import sqlite3

from bankbuddy.currency import parse_amount
from bankbuddy.database import connect_database, initialize_database
from bankbuddy.paths import AppPaths


class ImportFailure(ValueError):
    """Raised when a statement import cannot proceed."""


@dataclass(frozen=True)
class ParsedTransaction:
    """A normalized transaction staged from an import file."""

    transaction_date: str
    amount_minor_units: int
    description: str
    normalized_description: str
    check_number: str | None
    source_row_key: str


@dataclass(frozen=True)
class ImportSummary:
    """Import result counts for user-facing summaries."""

    file_name: str
    bank_name: str
    account_id: int
    rows_parsed: int
    rows_imported: int
    rows_skipped_duplicate: int


def parse_boa_csv(csv_path: Path) -> list[ParsedTransaction]:
    """Parse a Bank of America CSV export into normalized staged rows."""

    with csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ImportFailure("CSV file is missing headers.")
        headers = {header.strip().lower(): header for header in reader.fieldnames}
        date_header = required_header(headers, "date")
        description_header = required_header(headers, "description")
        amount_header = required_header(headers, "amount")
        check_header = optional_header(headers, "check number", "check #", "check")

        parsed_rows: list[ParsedTransaction] = []
        for row_number, row in enumerate(reader, start=2):
            description = row[description_header].strip()
            amount = parse_amount(row[amount_header], "USD")
            parsed_rows.append(
                ParsedTransaction(
                    transaction_date=parse_boa_date(row[date_header]),
                    amount_minor_units=amount.minor_units,
                    description=description,
                    normalized_description=normalize_description(description),
                    check_number=empty_to_none(row.get(check_header, ""))
                    if check_header
                    else None,
                    source_row_key=str(row_number),
                )
            )
    return parsed_rows


def import_boa_csv(
    paths: AppPaths,
    csv_path: Path,
    *,
    account_id: int,
) -> ImportSummary:
    """Import a Bank of America CSV file for a configured account."""

    initialize_database(paths)
    parsed_rows = parse_boa_csv(csv_path)
    file_hash = hash_file(csv_path)

    with connect_database(paths) as conn:
        account = find_import_account(conn, account_id)
        if account is None:
            raise ImportFailure(f"Account id {account_id} is not configured.")
        if account["bank_name"] != "Bank of America" or account["currency"] != "USD":
            raise ImportFailure(
                "Bank of America CSV import requires a Bank of America USD account."
            )

        bank_id = int(account["bank_id"])
        category_id = uncategorized_category_id(conn)
        file_id = ensure_import_file(
            conn,
            file_name=csv_path.name,
            file_hash=file_hash,
            bank_id=bank_id,
        )

        rows_imported = 0
        rows_skipped_duplicate = 0
        for parsed in parsed_rows:
            try:
                conn.execute(
                    """
                    insert into transactions (
                        account_id,
                        category_id,
                        file_id,
                        transaction_date,
                        amount_minor_units,
                        currency,
                        description,
                        normalized_description,
                        check_number,
                        source_row_key,
                        transaction_hash,
                        transfer_status
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account_id,
                        category_id,
                        file_id,
                        parsed.transaction_date,
                        parsed.amount_minor_units,
                        "USD",
                        parsed.description,
                        parsed.normalized_description,
                        parsed.check_number,
                        parsed.source_row_key,
                        transaction_hash(parsed),
                        "none",
                    ),
                )
            except sqlite3.IntegrityError:
                rows_skipped_duplicate += 1
            else:
                rows_imported += 1

        conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                import_status,
                finished_at,
                rows_parsed,
                rows_imported,
                rows_skipped_duplicate
            ) values (?, ?, ?, current_timestamp, ?, ?, ?)
            """,
            (
                file_id,
                bank_id,
                "success",
                len(parsed_rows),
                rows_imported,
                rows_skipped_duplicate,
            ),
        )
        conn.execute(
            """
            update import_files
            set last_success_at = current_timestamp,
                updated_at = current_timestamp
            where file_id = ?
            """,
            (file_id,),
        )
        conn.commit()

    return ImportSummary(
        file_name=csv_path.name,
        bank_name="Bank of America",
        account_id=account_id,
        rows_parsed=len(parsed_rows),
        rows_imported=rows_imported,
        rows_skipped_duplicate=rows_skipped_duplicate,
    )


def required_header(headers: dict[str, str], name: str) -> str:
    """Return a required CSV header by normalized name."""

    try:
        return headers[name]
    except KeyError as exc:
        raise ImportFailure(f"Bank of America CSV is missing required header: {name}") from exc


def optional_header(headers: dict[str, str], *names: str) -> str | None:
    """Return the first matching optional CSV header."""

    for name in names:
        if name in headers:
            return headers[name]
    return None


def parse_boa_date(value: str) -> str:
    """Parse a Bank of America CSV date into ISO format."""

    stripped = value.strip()
    for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(stripped, date_format).date().isoformat()
        except ValueError:
            continue
    raise ImportFailure(f"Invalid Bank of America transaction date: {value}")


def normalize_description(description: str) -> str:
    """Normalize transaction descriptions for hashing and matching."""

    return " ".join(description.lower().split())


def hash_file(path: Path) -> str:
    """Return the SHA-256 hash for a file."""

    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def transaction_hash(parsed: ParsedTransaction) -> str:
    """Return a stable fallback transaction hash for Bank of America CSV rows."""

    parts = [
        "boa_csv",
        parsed.transaction_date,
        str(parsed.amount_minor_units),
        parsed.normalized_description,
        parsed.check_number or "",
    ]
    return sha256("|".join(parts).encode("utf-8")).hexdigest()


def find_import_account(conn: sqlite3.Connection, account_id: int) -> sqlite3.Row | None:
    """Find a configured account with its bank metadata."""

    return conn.execute(
        """
        select
            accounts.account_id,
            accounts.currency,
            banks.bank_id,
            banks.bank_name
        from accounts
        join banks using (bank_id)
        where accounts.account_id = ?
        """,
        (account_id,),
    ).fetchone()


def uncategorized_category_id(conn: sqlite3.Connection) -> int:
    """Return the built-in Uncategorized category id."""

    row = conn.execute(
        "select category_id from categories where category_name = ?",
        ("Uncategorized",),
    ).fetchone()
    if row is None:
        raise ImportFailure("Built-in Uncategorized category is missing.")
    return int(row["category_id"])


def ensure_import_file(
    conn: sqlite3.Connection,
    *,
    file_name: str,
    file_hash: str,
    bank_id: int,
) -> int:
    """Return an import file id, creating it when first seen."""

    row = conn.execute(
        "select file_id from import_files where file_hash = ?",
        (file_hash,),
    ).fetchone()
    if row is not None:
        file_id = int(row["file_id"])
        conn.execute(
            """
            update import_files
            set file_name = ?,
                bank_id = ?,
                updated_at = current_timestamp
            where file_id = ?
            """,
            (file_name, bank_id, file_id),
        )
        return file_id

    cursor = conn.execute(
        """
        insert into import_files (file_name, file_hash, bank_id)
        values (?, ?, ?)
        """,
        (file_name, file_hash, bank_id),
    )
    return int(cursor.lastrowid)


def empty_to_none(value: str | None) -> str | None:
    """Normalize empty imported fields to NULL."""

    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
