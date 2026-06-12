"""Statement import helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re
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


ACCOUNT_NUMBER_PATTERN = re.compile(
    r"\b(?:account|acct)\s*(?:number|no\.?|#)?\s*[:#]?\s*((?:\d[\s-]*){6,})",
    re.IGNORECASE,
)
PDF_TRANSACTION_LINE_PATTERN = re.compile(
    r"^\s*(?P<date>\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+(?P<rest>.+?)\s*$"
)
PDF_MONEY_PATTERN = re.compile(r"-?\$?\d[\d,]*\.\d{2}|\(\$?\d[\d,]*\.\d{2}\)")


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


def parse_boa_pdf_text(text: str) -> list[ParsedTransaction]:
    """Parse extracted Bank of America PDF text into normalized staged rows."""

    if "bank of america" not in text.lower():
        raise ImportFailure("PDF does not look like a Bank of America statement.")

    statement_year = extract_statement_year(text)
    parsed_rows: list[ParsedTransaction] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = PDF_TRANSACTION_LINE_PATTERN.match(line)
        if match is None:
            continue

        rest = match.group("rest").strip()
        amount_match = transaction_amount_match(rest)
        if amount_match is None:
            continue

        description = rest[: amount_match.start()].strip()
        if not description:
            continue

        amount = parse_amount(clean_pdf_amount(amount_match.group()), "USD")
        parsed_rows.append(
            ParsedTransaction(
                transaction_date=parse_boa_pdf_date(
                    match.group("date"),
                    statement_year=statement_year,
                ),
                amount_minor_units=amount.minor_units,
                description=description,
                normalized_description=normalize_description(description),
                check_number=None,
                source_row_key=str(line_number),
            )
        )

    if not parsed_rows:
        raise ImportFailure("Bank of America PDF has no parseable transactions.")
    return parsed_rows


def extract_boa_pdf_account_number(text: str) -> str:
    """Return the normalized full account number from BOA PDF text."""

    match = ACCOUNT_NUMBER_PATTERN.search(text)
    if match is None:
        raise ImportFailure("Bank of America PDF is missing an account number.")

    account_number = normalize_account_number(match.group(1))
    if not account_number:
        raise ImportFailure("Bank of America PDF account number is invalid.")
    return account_number


def normalize_account_number(value: str) -> str:
    """Normalize account identifiers for strict matching."""

    return "".join(char for char in value if char.isdigit())


def import_boa_csv(
    paths: AppPaths,
    csv_path: Path,
    *,
    account_id: int,
) -> ImportSummary:
    """Import a Bank of America CSV file for a configured account."""

    initialize_database(paths)
    parsed_rows = parse_boa_csv(csv_path)
    return import_boa_transactions(
        paths,
        csv_path,
        account_id=account_id,
        parsed_rows=parsed_rows,
        source_format="boa_csv",
        import_label="CSV",
        require_pdf_account_match=False,
    )


def import_boa_pdf(
    paths: AppPaths,
    pdf_path: Path,
    *,
    account_id: int,
) -> ImportSummary:
    """Import a Bank of America text-selectable PDF for a configured account."""

    initialize_database(paths)
    text = extract_pdf_text(pdf_path)
    parsed_rows = parse_boa_pdf_text(text)
    pdf_account_number = extract_boa_pdf_account_number(text)
    return import_boa_transactions(
        paths,
        pdf_path,
        account_id=account_id,
        parsed_rows=parsed_rows,
        source_format="boa_pdf",
        import_label="PDF",
        require_pdf_account_match=True,
        pdf_account_number=pdf_account_number,
    )


def import_boa_transactions(
    paths: AppPaths,
    import_path: Path,
    *,
    account_id: int,
    parsed_rows: list[ParsedTransaction],
    source_format: str,
    import_label: str,
    require_pdf_account_match: bool,
    pdf_account_number: str | None = None,
) -> ImportSummary:
    """Persist parsed Bank of America transactions for a configured account."""

    file_hash = hash_file(import_path)

    with connect_database(paths) as conn:
        account = find_import_account(conn, account_id)
        if account is None:
            raise ImportFailure(f"Account id {account_id} is not configured.")
        if account["bank_name"] != "Bank of America" or account["currency"] != "USD":
            raise ImportFailure(
                f"Bank of America {import_label} import requires a "
                "Bank of America USD account."
            )
        if require_pdf_account_match:
            configured_account_number = normalize_account_number(account["account_number"])
            if pdf_account_number != configured_account_number:
                raise ImportFailure(
                    "Bank of America PDF account number does not match configured account."
                )

        bank_id = int(account["bank_id"])
        category_id = uncategorized_category_id(conn)
        file_id = ensure_import_file(
            conn,
            file_name=import_path.name,
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
                        transaction_hash(parsed, source_format=source_format),
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
        file_name=import_path.name,
        bank_name="Bank of America",
        account_id=account_id,
        rows_parsed=len(parsed_rows),
        rows_imported=rows_imported,
        rows_skipped_duplicate=rows_skipped_duplicate,
    )


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a machine-generated PDF."""

    import pdfplumber

    extracted_pages: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                extracted_pages.append(page.extract_text() or "")
    except Exception as exc:
        raise ImportFailure(f"Unable to read PDF file: {pdf_path}") from exc

    text = "\n".join(extracted_pages).strip()
    if not text:
        raise ImportFailure("PDF contains no selectable text.")
    return text


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
    for date_format in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(stripped, date_format).date().isoformat()
        except ValueError:
            continue
    raise ImportFailure(f"Invalid Bank of America transaction date: {value}")


def parse_boa_pdf_date(value: str, *, statement_year: int) -> str:
    """Parse a Bank of America PDF transaction date into ISO format."""

    stripped = value.strip()
    if stripped.count("/") == 1:
        stripped = f"{stripped}/{statement_year}"
    return parse_boa_date(stripped)


def extract_statement_year(text: str) -> int:
    """Return the statement year used for PDF rows that omit the year."""

    years = [int(year) for year in re.findall(r"\b(20\d{2})\b", text)]
    if not years:
        raise ImportFailure("Bank of America PDF is missing a statement year.")
    return years[-1]


def transaction_amount_match(rest: str) -> re.Match[str] | None:
    """Return the transaction amount match from a PDF transaction line."""

    matches = list(PDF_MONEY_PATTERN.finditer(rest))
    if not matches:
        return None
    if len(matches) >= 2:
        return matches[-2]
    return matches[-1]


def clean_pdf_amount(value: str) -> str:
    """Normalize statement-style amount text for currency parsing."""

    stripped = value.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        return "-" + stripped[1:-1]
    return stripped


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


def transaction_hash(parsed: ParsedTransaction, *, source_format: str = "boa_csv") -> str:
    """Return a stable fallback transaction hash for Bank of America rows."""

    parts = [
        source_format,
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
            accounts.account_number,
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
