"""Duplicate transaction diagnostic helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Callable

from bankbuddy.accounts import masked_account_number
from bankbuddy.database import connect_database
from bankbuddy.database import initialize_database
from bankbuddy.imports import extract_pdf_text
from bankbuddy.imports import parse_boa_csv
from bankbuddy.imports import parse_boa_pdf_text
from bankbuddy.imports import ParsedTransaction
from bankbuddy.imports import transaction_hash
from bankbuddy.paths import AppPaths
from bankbuddy.transactions import resolve_account_last4
from bankbuddy.transactions import TransactionFilterError


@dataclass(frozen=True)
class DuplicateDiagnosticRow:
    """One reconstructed skipped duplicate candidate and its matching row."""

    attempt_id: int
    file_id: int
    source_format: str
    bank_name: str
    account_id: int
    account_display: str
    statement_start_date: str
    statement_end_date: str
    file_name: str
    candidate_source_row_key: str
    candidate_date: str
    candidate_amount_minor_units: int
    candidate_description: str
    matched_transaction_id: int
    matched_source_row_key: str | None
    matched_date: str
    matched_amount_minor_units: int
    matched_description: str

    @property
    def statement_period(self) -> str:
        """Return the inclusive statement period label."""

        return f"{self.statement_start_date} to {self.statement_end_date}"


@dataclass(frozen=True)
class DuplicateAttempt:
    """A successful import attempt with skipped duplicate rows."""

    attempt_id: int
    file_id: int
    source_format: str
    processed_path: str
    bank_name: str
    account_id: int
    account_display: str
    statement_start_date: str
    statement_end_date: str
    file_name: str
    started_at: str
    rows_skipped_duplicate: int
    rows_imported: int


@dataclass(frozen=True)
class DuplicateParserAdapter:
    """Parser hook for a source format that supports duplicate diagnostics."""

    source_format: str
    parse_file: Callable[[Path], list[ParsedTransaction]]


class DuplicateDiagnosticError(ValueError):
    """Raised when duplicate diagnostics cannot be reconstructed."""


def list_duplicate_transaction_diagnostics(
    paths: AppPaths,
    *,
    bank_name: str | None = None,
    account_id: int | None = None,
    account_last4: str | None = None,
    year: int | None = None,
    attempt_id: int | None = None,
    file_id: int | None = None,
) -> list[DuplicateDiagnosticRow]:
    """Return reconstructed duplicate transaction diagnostics."""

    initialize_database(paths)
    selected_account_id = resolve_duplicate_account_filter(
        paths,
        account_id=account_id,
        account_last4=account_last4,
    )
    with connect_database(paths) as conn:
        attempts = duplicate_attempts(
            conn,
            bank_name=bank_name,
            account_id=selected_account_id,
            year=year,
            attempt_id=attempt_id,
            file_id=file_id,
        )
        diagnostics: list[DuplicateDiagnosticRow] = []
        for attempt in attempts:
            diagnostics.extend(reconstruct_attempt_duplicates(conn, paths, attempt))
    return diagnostics


def resolve_duplicate_account_filter(
    paths: AppPaths,
    *,
    account_id: int | None,
    account_last4: str | None,
) -> int | None:
    """Resolve account filter options into one optional account id."""

    if account_id is not None and account_last4 is not None:
        raise DuplicateDiagnosticError(
            "Use either --account-id or --account-last4, not both."
        )
    if account_last4 is None:
        return account_id
    try:
        return resolve_account_last4(paths, account_last4)
    except TransactionFilterError as exc:
        raise DuplicateDiagnosticError(str(exc)) from exc


def duplicate_attempts(
    conn: sqlite3.Connection,
    *,
    bank_name: str | None,
    account_id: int | None,
    year: int | None,
    attempt_id: int | None,
    file_id: int | None,
) -> list[DuplicateAttempt]:
    """Return successful import attempts that reported skipped duplicate rows."""

    conditions = [
        "import_attempts.import_status = 'success'",
        "import_attempts.rows_skipped_duplicate > 0",
        "import_attempts.account_id is not null",
        "import_files.processed_path is not null",
        "import_files.source_format is not null",
        "import_files.statement_start_date is not null",
        "import_files.statement_end_date is not null",
    ]
    parameters: list[object] = []
    if bank_name is not None:
        normalized_bank_name = bank_name.strip()
        if not normalized_bank_name:
            raise DuplicateDiagnosticError("Bank name must not be empty.")
        conditions.append("lower(banks.bank_name) = lower(?)")
        parameters.append(normalized_bank_name)
    if account_id is not None:
        conditions.append("accounts.account_id = ?")
        parameters.append(account_id)
    if year is not None:
        conditions.append("substr(import_files.statement_end_date, 1, 4) = ?")
        parameters.append(f"{year:04d}")
    if attempt_id is not None:
        conditions.append("import_attempts.attempt_id = ?")
        parameters.append(attempt_id)
    if file_id is not None:
        conditions.append("import_files.file_id = ?")
        parameters.append(file_id)

    rows = conn.execute(
        f"""
        select
            import_attempts.attempt_id,
            import_attempts.file_id,
            import_attempts.account_id,
            import_attempts.started_at,
            import_attempts.rows_skipped_duplicate,
            import_attempts.rows_imported,
            import_files.source_format,
            import_files.processed_path,
            import_files.statement_start_date,
            import_files.statement_end_date,
            coalesce(
                import_files.canonical_file_name,
                import_files.file_name
            ) as file_name,
            banks.bank_name,
            accounts.account_number,
            accounts.display_name
        from import_attempts
        join import_files using (file_id)
        join accounts on accounts.account_id = import_attempts.account_id
        join banks on banks.bank_id = accounts.bank_id
        where {' and '.join(conditions)}
        order by
            import_files.statement_end_date,
            import_attempts.attempt_id
        """,
        parameters,
    ).fetchall()

    return [
        DuplicateAttempt(
            attempt_id=int(row["attempt_id"]),
            file_id=int(row["file_id"]),
            source_format=row["source_format"],
            processed_path=row["processed_path"],
            bank_name=row["bank_name"],
            account_id=int(row["account_id"]),
            account_display=row["display_name"]
            or masked_account_number(row["account_number"]),
            statement_start_date=row["statement_start_date"],
            statement_end_date=row["statement_end_date"],
            file_name=row["file_name"],
            started_at=row["started_at"],
            rows_skipped_duplicate=int(row["rows_skipped_duplicate"]),
            rows_imported=int(row["rows_imported"]),
        )
        for row in rows
    ]


def reconstruct_attempt_duplicates(
    conn: sqlite3.Connection,
    paths: AppPaths,
    attempt: DuplicateAttempt,
) -> list[DuplicateDiagnosticRow]:
    """Reparse an import attempt's statement and find skipped duplicate rows."""

    adapter = duplicate_parser_adapter(attempt.source_format)
    processed_path = paths.root / attempt.processed_path
    if not processed_path.exists():
        raise DuplicateDiagnosticError(
            f"Archived statement file is missing: {attempt.processed_path}"
        )
    parsed_rows = adapter.parse_file(processed_path)
    matches = matching_transactions_by_hash(conn, attempt, parsed_rows)
    diagnostics = duplicate_rows_from_matches(attempt, parsed_rows, matches)
    if len(diagnostics) < attempt.rows_skipped_duplicate:
        diagnostics = backfill_duplicate_rows_from_matches(
            attempt,
            parsed_rows,
            matches,
            diagnostics,
        )
    return diagnostics[: attempt.rows_skipped_duplicate]


def duplicate_rows_from_matches(
    attempt: DuplicateAttempt,
    parsed_rows: list[ParsedTransaction],
    matches: dict[str, sqlite3.Row],
) -> list[DuplicateDiagnosticRow]:
    """Return rows that can be confidently reconstructed as duplicates."""

    diagnostics: list[DuplicateDiagnosticRow] = []
    seen_hashes: set[str] = set()
    for parsed in parsed_rows:
        parsed_hash = transaction_hash(parsed, source_format=attempt.source_format)
        match = matches.get(parsed_hash)
        if match is None:
            seen_hashes.add(parsed_hash)
            continue

        duplicate_by_statement = parsed_hash in seen_hashes
        duplicate_by_existing_row = (
            attempt.rows_imported == 0
            or int(match["file_id"]) != attempt.file_id
            or match["created_at"] < attempt.started_at
        )
        if duplicate_by_statement or duplicate_by_existing_row:
            diagnostics.append(
                diagnostic_row_from_match(attempt, parsed, match)
            )
        seen_hashes.add(parsed_hash)
    return diagnostics


def backfill_duplicate_rows_from_matches(
    attempt: DuplicateAttempt,
    parsed_rows: list[ParsedTransaction],
    matches: dict[str, sqlite3.Row],
    diagnostics: list[DuplicateDiagnosticRow],
) -> list[DuplicateDiagnosticRow]:
    """Fill ambiguous diagnostics from matching rows when timestamps are insufficient."""

    existing_keys = {
        (
            row.attempt_id,
            row.candidate_source_row_key,
            row.matched_transaction_id,
        )
        for row in diagnostics
    }
    filled = list(diagnostics)
    for parsed in parsed_rows:
        parsed_hash = transaction_hash(parsed, source_format=attempt.source_format)
        match = matches.get(parsed_hash)
        if match is None:
            continue
        key = (
            attempt.attempt_id,
            parsed.source_row_key,
            int(match["transaction_id"]),
        )
        if key in existing_keys:
            continue
        filled.append(diagnostic_row_from_match(attempt, parsed, match))
        existing_keys.add(key)
        if len(filled) >= attempt.rows_skipped_duplicate:
            break
    return filled


def matching_transactions_by_hash(
    conn: sqlite3.Connection,
    attempt: DuplicateAttempt,
    parsed_rows: list[ParsedTransaction],
) -> dict[str, sqlite3.Row]:
    """Return stored transactions keyed by parsed transaction hash."""

    hashes = [
        transaction_hash(parsed, source_format=attempt.source_format)
        for parsed in parsed_rows
    ]
    if not hashes:
        return {}
    placeholders = ", ".join("?" for _hash in hashes)
    rows = conn.execute(
        f"""
        select
            transaction_id,
            file_id,
            transaction_date,
            amount_minor_units,
            description,
            source_row_key,
            transaction_hash,
            created_at
        from transactions
        where account_id = ?
          and transaction_hash in ({placeholders})
        order by transaction_id
        """,
        [attempt.account_id, *hashes],
    ).fetchall()
    return {row["transaction_hash"]: row for row in rows}


def diagnostic_row_from_match(
    attempt: DuplicateAttempt,
    parsed: ParsedTransaction,
    match: sqlite3.Row,
) -> DuplicateDiagnosticRow:
    """Build one user-facing diagnostic row from a parsed row and DB match."""

    return DuplicateDiagnosticRow(
        attempt_id=attempt.attempt_id,
        file_id=attempt.file_id,
        source_format=attempt.source_format,
        bank_name=attempt.bank_name,
        account_id=attempt.account_id,
        account_display=attempt.account_display,
        statement_start_date=attempt.statement_start_date,
        statement_end_date=attempt.statement_end_date,
        file_name=attempt.file_name,
        candidate_source_row_key=parsed.source_row_key,
        candidate_date=parsed.transaction_date,
        candidate_amount_minor_units=parsed.amount_minor_units,
        candidate_description=parsed.description,
        matched_transaction_id=int(match["transaction_id"]),
        matched_source_row_key=match["source_row_key"],
        matched_date=match["transaction_date"],
        matched_amount_minor_units=int(match["amount_minor_units"]),
        matched_description=match["description"],
    )


def duplicate_parser_adapter(source_format: str) -> DuplicateParserAdapter:
    """Return the parser adapter for a duplicate diagnostic source format."""

    adapters = duplicate_parser_adapters()
    adapter = adapters.get(source_format)
    if adapter is None:
        raise DuplicateDiagnosticError(
            f"Duplicate diagnostics do not support source format: {source_format}"
        )
    return adapter


def duplicate_parser_adapters() -> dict[str, DuplicateParserAdapter]:
    """Return duplicate diagnostic parser adapters keyed by source format."""

    return {
        "boa_csv": DuplicateParserAdapter(
            source_format="boa_csv",
            parse_file=parse_boa_csv,
        ),
        "boa_pdf": DuplicateParserAdapter(
            source_format="boa_pdf",
            parse_file=parse_boa_pdf_file,
        ),
    }


def parse_boa_pdf_file(path: Path) -> list[ParsedTransaction]:
    """Parse a Bank of America PDF from an archived file path."""

    return parse_boa_pdf_text(extract_pdf_text(path))
