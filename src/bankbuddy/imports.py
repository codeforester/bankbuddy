"""Statement import helpers."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
import logging
from pathlib import Path
import re
import sqlite3

from bankbuddy.currency import parse_amount
from bankbuddy.database import connect_database, initialize_database
from bankbuddy.import_files import ImportFileMetadata
from bankbuddy.import_files import archive_statement_file
from bankbuddy.import_files import plan_statement_archive_file
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
    value_date: str | None = None
    balance_after_minor_units: int | None = None


@dataclass(frozen=True)
class ParsedStatement:
    """A normalized statement staged from an import file."""

    bank_name: str
    account_number: str
    currency: str
    statement_start_date: str
    statement_end_date: str
    transactions: list[ParsedTransaction]
    latest_balance_minor_units: int | None = None
    latest_balance_as_of_date: str | None = None


@dataclass(frozen=True)
class ImportSummary:
    """Import result counts for user-facing summaries."""

    file_name: str
    bank_name: str
    account_id: int
    rows_parsed: int
    rows_imported: int
    rows_skipped_duplicate: int
    latest_balance_minor_units: int | None = None
    latest_balance_currency: str | None = None
    latest_balance_as_of_date: str | None = None


@dataclass(frozen=True)
class ImportPlan:
    """Read-only import plan counts for dry-run summaries."""

    file_name: str
    bank_name: str
    account_id: int
    rows_parsed: int
    rows_would_import: int
    rows_already_present: int
    canonical_file_name: str
    processed_path: str
    latest_balance_minor_units: int | None = None
    latest_balance_currency: str | None = None
    latest_balance_as_of_date: str | None = None


@dataclass(frozen=True)
class SuccessfulImportFile:
    """Metadata for a file that was already imported successfully."""

    file_id: int
    bank_id: int
    bank_name: str
    account_id: int | None
    canonical_file_name: str
    processed_path: str
    statement_end_date: str


ACCOUNT_NUMBER_PATTERN = re.compile(
    r"\b(?:account|acct)\s*(?:number|no\.?|#)?\s*[:#]?\s*((?:\d[\s-]*){6,})",
    re.IGNORECASE,
)
PDF_TRANSACTION_LINE_PATTERN = re.compile(
    r"^\s*(?P<date>\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+(?P<rest>.+?)\s*$"
)
PDF_MONEY_PATTERN = re.compile(r"-?\$?\d[\d,]*\.\d{2}|\(\$?\d[\d,]*\.\d{2}\)")
PDF_TRANSACTION_CONTINUATION_PATTERN = re.compile(r"^\s*(?:ID|CO\s+ID)\s*:", re.IGNORECASE)
BOA_STATEMENT_HEADER_DATE = r"[A-Za-z]+\s+\d{1,2},\s+\d{4}"
BOA_STATEMENT_PERIOD_PATTERN = re.compile(
    r"Statement\s+Period:\s*"
    rf"(?P<start>{BOA_STATEMENT_HEADER_DATE})\s+through\s+"
    rf"(?P<end>{BOA_STATEMENT_HEADER_DATE})",
    re.IGNORECASE,
)
BOA_ACCOUNT_HEADER_PERIOD_PATTERN = re.compile(
    r"\bfor\s+"
    rf"(?P<start>{BOA_STATEMENT_HEADER_DATE})\s+to\s+"
    rf"(?P<end>{BOA_STATEMENT_HEADER_DATE})\s+"
    r"Account\s+number\b",
    re.IGNORECASE,
)
BOA_COMBINED_STATEMENT_PERIOD_PATTERN = re.compile(
    r"Your\s+combined\s+statement\s+for\s+"
    rf"(?P<start>{BOA_STATEMENT_HEADER_DATE})\s+to\s+"
    rf"(?P<end>{BOA_STATEMENT_HEADER_DATE})",
    re.IGNORECASE,
)
BOA_LEGACY_ACCOUNT_HEADER_PERIOD_PATTERN = re.compile(
    r"Account\s*#\s*(?:\d[\s-]*){6,}!\s*"
    rf"(?P<start>{BOA_STATEMENT_HEADER_DATE})\s+to\s+"
    rf"(?P<end>{BOA_STATEMENT_HEADER_DATE})",
    re.IGNORECASE,
)
BOA_STATEMENT_PERIOD_PATTERNS = (
    BOA_STATEMENT_PERIOD_PATTERN,
    BOA_ACCOUNT_HEADER_PERIOD_PATTERN,
    BOA_COMBINED_STATEMENT_PERIOD_PATTERN,
    BOA_LEGACY_ACCOUNT_HEADER_PERIOD_PATTERN,
)
ICICI_BANK_NAME = "ICICI Bank"
ICICI_SOURCE_FORMAT = "icici_xls"
ICICI_ACCOUNT_NUMBER_PATTERN = re.compile(
    r"\b(?:account|acct|a/c)\s*(?:number|no\.?|#)?\s*[:#-]?\s*"
    r"((?:\d[\s-]*){6,})",
    re.IGNORECASE,
)
ICICI_DATE_TOKEN_PATTERN = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
    r"|\b\d{1,2}-[A-Za-z]{3,9}-\d{2,4}\b"
)
ICICI_HEADER_ALIASES = {
    "valuedate": "value_date",
    "transactiondate": "transaction_date",
    "chequenumber": "check_number",
    "chqno": "check_number",
    "transactionremarks": "description",
    "remarks": "description",
    "withdrawalamountinr": "withdrawal",
    "withdrawal": "withdrawal",
    "depositamountinr": "deposit",
    "deposit": "deposit",
    "balanceinr": "balance",
    "balance": "balance",
}
ICICI_REQUIRED_FIELDS = {
    "value_date",
    "transaction_date",
    "description",
    "withdrawal",
    "deposit",
    "balance",
}


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


def parse_icici_xls(xls_path: Path) -> ParsedStatement:
    """Parse an ICICI Bank old-format Excel export into a normalized statement."""

    try:
        import xlrd
    except ImportError as exc:
        raise ImportFailure("ICICI XLS import requires the xlrd package.") from exc

    try:
        workbook = xlrd.open_workbook(str(xls_path))
    except Exception as exc:
        raise ImportFailure(f"Unable to read ICICI XLS file: {xls_path}") from exc

    errors: list[str] = []
    for sheet in workbook.sheets():
        rows = xls_sheet_rows(sheet, datemode=workbook.datemode, xlrd_module=xlrd)
        try:
            return parse_icici_xls_rows(rows)
        except ImportFailure as exc:
            errors.append(str(exc))

    detail = errors[-1] if errors else "workbook has no sheets"
    raise ImportFailure(f"ICICI XLS could not be parsed: {detail}")


def xls_sheet_rows(sheet, *, datemode: int, xlrd_module) -> list[list[object]]:
    """Return sheet rows with Excel date cells converted to dates."""

    rows: list[list[object]] = []
    for row_index in range(sheet.nrows):
        row_values: list[object] = []
        for col_index in range(sheet.ncols):
            cell = sheet.cell(row_index, col_index)
            if cell.ctype == xlrd_module.XL_CELL_DATE:
                row_values.append(
                    xlrd_module.xldate_as_datetime(cell.value, datemode).date()
                )
            else:
                row_values.append(cell.value)
        rows.append(row_values)
    return rows


def parse_icici_xls_rows(rows: Sequence[Sequence[object]]) -> ParsedStatement:
    """Parse normalized ICICI worksheet rows into statement metadata and rows."""

    normalized_rows = [
        [cell_to_text(cell) for cell in row]
        for row in rows
    ]
    header_index, columns = find_icici_header(normalized_rows)
    account_number = extract_icici_account_number(normalized_rows[:header_index])
    parsed_rows: list[ParsedTransaction] = []
    previous_balance: int | None = None

    for source_row_number, row in enumerate(
        normalized_rows[header_index + 1 :],
        start=header_index + 2,
    ):
        if is_empty_row(row):
            continue
        transaction_date_text = cell_at(row, columns["transaction_date"])
        value_date_text = cell_at(row, columns["value_date"])
        description = cell_at(row, columns["description"])
        withdrawal_text = cell_at(row, columns["withdrawal"])
        deposit_text = cell_at(row, columns["deposit"])
        balance_text = cell_at(row, columns["balance"])
        if not transaction_date_text and not description:
            continue
        if (
            not transaction_date_text
            and not value_date_text
            and description
            and not withdrawal_text
            and not deposit_text
            and not balance_text
        ):
            if not parsed_rows:
                raise ImportFailure(
                    "ICICI XLS has a description continuation before any "
                    f"transaction at row {source_row_number}."
                )
            previous = parsed_rows[-1]
            continued_description = f"{previous.description} {description}"
            parsed_rows[-1] = replace(
                previous,
                description=continued_description,
                normalized_description=normalize_description(continued_description),
                source_row_key=f"{previous.source_row_key},{source_row_number}",
            )
            continue
        if not description:
            raise ImportFailure(
                f"ICICI XLS row {source_row_number} is missing transaction remarks."
            )

        amount_minor_units = parse_icici_row_amount(
            withdrawal_text,
            deposit_text,
            source_row_number=source_row_number,
        )
        balance_after = parse_optional_icici_amount(
            balance_text,
            field_name="balance",
            source_row_number=source_row_number,
        )
        if previous_balance is not None and balance_after is not None:
            expected_balance = previous_balance + amount_minor_units
            if expected_balance != balance_after:
                raise ImportFailure(
                    "ICICI XLS balance does not reconcile at row "
                    f"{source_row_number}: expected {expected_balance}, "
                    f"found {balance_after}."
                )
        if balance_after is not None:
            previous_balance = balance_after

        parsed_rows.append(
            ParsedTransaction(
                transaction_date=parse_icici_date(
                    transaction_date_text,
                    field_name="transaction date",
                    source_row_number=source_row_number,
                ),
                value_date=parse_icici_date(
                    value_date_text,
                    field_name="value date",
                    source_row_number=source_row_number,
                ),
                amount_minor_units=amount_minor_units,
                description=description,
                normalized_description=normalize_description(description),
                check_number=empty_to_none(cell_at(row, columns.get("check_number"))),
                source_row_key=str(source_row_number),
                balance_after_minor_units=balance_after,
            )
        )

    if not parsed_rows:
        raise ImportFailure("ICICI XLS has no parseable transactions.")

    statement_start_date, statement_end_date = extract_icici_statement_period(
        normalized_rows[:header_index],
        parsed_rows,
    )
    latest_balance = latest_icici_balance(parsed_rows)
    return ParsedStatement(
        bank_name=ICICI_BANK_NAME,
        account_number=account_number,
        currency="INR",
        statement_start_date=statement_start_date,
        statement_end_date=statement_end_date,
        transactions=parsed_rows,
        latest_balance_minor_units=latest_balance,
        latest_balance_as_of_date=statement_end_date if latest_balance is not None else None,
    )


def parse_boa_pdf_text(text: str) -> list[ParsedTransaction]:
    """Parse extracted Bank of America PDF text into normalized staged rows."""

    if "bank of america" not in text.lower():
        raise ImportFailure("PDF does not look like a Bank of America statement.")

    statement_year = extract_statement_year(text)
    parsed_rows: list[ParsedTransaction] = []
    pending_transaction_date: str | None = None
    pending_amount_minor_units: int | None = None
    pending_source_row_key: str | None = None
    pending_description_lines: list[str] = []

    def flush_pending_transaction() -> None:
        nonlocal pending_transaction_date
        nonlocal pending_amount_minor_units
        nonlocal pending_source_row_key
        if (
            pending_transaction_date is None
            or pending_amount_minor_units is None
            or pending_source_row_key is None
        ):
            return
        description = " ".join(pending_description_lines)
        parsed_rows.append(
            ParsedTransaction(
                transaction_date=pending_transaction_date,
                amount_minor_units=pending_amount_minor_units,
                description=description,
                normalized_description=normalize_description(description),
                check_number=None,
                source_row_key=pending_source_row_key,
            )
        )
        pending_transaction_date = None
        pending_amount_minor_units = None
        pending_source_row_key = None
        pending_description_lines.clear()

    for line_number, line in enumerate(text.splitlines(), start=1):
        match = PDF_TRANSACTION_LINE_PATTERN.match(line)
        if match is None:
            if pending_description_lines and is_pdf_transaction_continuation(line):
                pending_description_lines.append(line.strip())
            continue

        rest = match.group("rest").strip()
        amount_match = transaction_amount_match(rest)
        if amount_match is None:
            if pending_description_lines and is_pdf_transaction_continuation(line):
                pending_description_lines.append(line.strip())
            continue

        description = rest[: amount_match.start()].strip()
        if not description:
            continue

        flush_pending_transaction()
        amount = parse_amount(clean_pdf_amount(amount_match.group()), "USD")
        pending_transaction_date = parse_boa_pdf_date(
            match.group("date"),
            statement_year=statement_year,
        )
        pending_amount_minor_units = amount.minor_units
        pending_source_row_key = str(line_number)
        pending_description_lines.append(description)

    flush_pending_transaction()

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


def extract_boa_pdf_statement_period(text: str) -> tuple[str, str]:
    """Return the statement period from a Bank of America PDF header."""

    match = None
    for pattern in BOA_STATEMENT_PERIOD_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            break
    if match is None:
        raise ImportFailure(
            "Bank of America PDF statement period was not found in extracted text. "
            "Supported headers include 'Statement Period: <Month D, YYYY> through "
            "<Month D, YYYY>', 'for <Month D, YYYY> to <Month D, YYYY> Account "
            "number', and 'Your combined statement' followed by 'for <Month D, "
            "YYYY> to <Month D, YYYY>'."
        )
    return (
        parse_statement_header_date(match.group("start")).isoformat(),
        parse_statement_header_date(match.group("end")).isoformat(),
    )


def find_icici_header(rows: Sequence[Sequence[str]]) -> tuple[int, dict[str, int]]:
    """Return the ICICI transaction table header index and normalized columns."""

    for row_index, row in enumerate(rows):
        columns: dict[str, int] = {}
        for column_index, cell in enumerate(row):
            field_name = ICICI_HEADER_ALIASES.get(normalize_icici_header(cell))
            if field_name is not None and field_name not in columns:
                columns[field_name] = column_index
        if ICICI_REQUIRED_FIELDS.issubset(columns):
            return row_index, columns
    raise ImportFailure("ICICI XLS is missing the transaction table header.")


def normalize_icici_header(value: str) -> str:
    """Return a compact ICICI header key."""

    return re.sub(r"[^a-z0-9]+", "", value.lower())


def extract_icici_account_number(rows: Sequence[Sequence[str]]) -> str:
    """Return the normalized full account number from ICICI statement rows."""

    for row in rows:
        row_text = " ".join(cell for cell in row if cell)
        if "account" not in row_text.lower() and "a/c" not in row_text.lower():
            continue
        match = ICICI_ACCOUNT_NUMBER_PATTERN.search(row_text)
        if match is not None:
            account_number = normalize_account_number(match.group(1))
            if account_number:
                return account_number
    raise ImportFailure("ICICI XLS is missing an account number.")


def extract_icici_statement_period(
    rows: Sequence[Sequence[str]],
    parsed_rows: list[ParsedTransaction],
) -> tuple[str, str]:
    """Return the ICICI statement period, falling back to transaction bounds."""

    for row in rows:
        row_text = " ".join(cell for cell in row if cell)
        lower_row_text = row_text.lower()
        if "period" not in lower_row_text and (
            "from" not in lower_row_text or "to" not in lower_row_text
        ):
            continue
        dates = [
            parse_icici_date(match.group(), field_name="statement period", source_row_number=0)
            for match in ICICI_DATE_TOKEN_PATTERN.finditer(row_text)
        ]
        if len(dates) >= 2:
            return dates[0], dates[1]

    return statement_period_from_rows(parsed_rows)


def parse_icici_date(
    value: str,
    *,
    field_name: str,
    source_row_number: int,
) -> str:
    """Parse an ICICI statement date into ISO format."""

    stripped = value.strip()
    for date_format in (
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d-%B-%Y",
        "%d-%B-%y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(stripped, date_format).date().isoformat()
        except ValueError:
            continue
    row_detail = f" at row {source_row_number}" if source_row_number else ""
    raise ImportFailure(f"Invalid ICICI {field_name}{row_detail}: {value}")


def parse_icici_row_amount(
    withdrawal_text: str,
    deposit_text: str,
    *,
    source_row_number: int,
) -> int:
    """Return a signed ICICI transaction amount from withdrawal/deposit columns."""

    withdrawal = parse_optional_icici_amount(
        withdrawal_text,
        field_name="withdrawal amount",
        source_row_number=source_row_number,
    )
    deposit = parse_optional_icici_amount(
        deposit_text,
        field_name="deposit amount",
        source_row_number=source_row_number,
    )
    if withdrawal == 0:
        withdrawal = None
    if deposit == 0:
        deposit = None
    if withdrawal is not None and deposit is not None:
        raise ImportFailure(
            f"ICICI XLS row {source_row_number} has both withdrawal and deposit amounts."
        )
    if withdrawal is None and deposit is None:
        raise ImportFailure(
            f"ICICI XLS row {source_row_number} is missing an amount."
        )
    if withdrawal is not None:
        return -abs(withdrawal)
    if deposit is None:
        raise ImportFailure(
            f"ICICI XLS row {source_row_number} is missing an amount."
        )
    return abs(deposit)


def parse_optional_icici_amount(
    value: str,
    *,
    field_name: str,
    source_row_number: int,
) -> int | None:
    """Parse an optional ICICI INR amount into minor units."""

    stripped = value.strip()
    if not stripped or stripped == "-":
        return None
    try:
        return parse_amount(stripped, "INR").minor_units
    except ValueError as exc:
        raise ImportFailure(
            f"Invalid ICICI {field_name} at row {source_row_number}: {value}"
        ) from exc


def latest_icici_balance(parsed_rows: list[ParsedTransaction]) -> int | None:
    """Return the final row balance from parsed ICICI transactions."""

    for row in reversed(parsed_rows):
        if row.balance_after_minor_units is not None:
            return row.balance_after_minor_units
    return None


def cell_at(row: Sequence[str], index: int | None) -> str:
    """Return stripped text for a possibly missing row index."""

    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def cell_to_text(value: object) -> str:
    """Normalize spreadsheet cell values for parser logic."""

    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def is_empty_row(row: Sequence[str]) -> bool:
    """Return whether a normalized spreadsheet row has no content."""

    return all(not cell.strip() for cell in row)


def normalize_account_number(value: str) -> str:
    """Normalize account identifiers for strict matching."""

    return "".join(char for char in value if char.isdigit())


def import_boa_csv(
    paths: AppPaths,
    csv_path: Path,
    *,
    account_id: int,
    logger: logging.Logger | None = None,
) -> ImportSummary:
    """Import a Bank of America CSV file for a configured account."""

    initialize_database(paths)
    log_debug(logger, "source_format=boa_csv parse_start file_name=%s", csv_path.name)
    try:
        parsed_rows = parse_boa_csv(csv_path)
        statement_start_date, statement_end_date = statement_period_from_rows(parsed_rows)
        log_debug(
            logger,
            "source_format=boa_csv parse_finished rows_parsed=%s",
            len(parsed_rows),
        )
        return import_boa_transactions(
            paths,
            csv_path,
            account_id=account_id,
            parsed_rows=parsed_rows,
            source_format="boa_csv",
            import_label="CSV",
            require_pdf_account_match=False,
            statement_start_date=statement_start_date,
            statement_end_date=statement_end_date,
            logger=logger,
        )
    except ImportFailure as exc:
        record_failed_import(
            paths,
            csv_path,
            source_format="boa_csv",
            error_message=str(exc),
            account_id=account_id,
        )
        raise


def import_boa_pdf(
    paths: AppPaths,
    pdf_path: Path,
    *,
    account_id: int,
    extracted_text: str | None = None,
    logger: logging.Logger | None = None,
) -> ImportSummary:
    """Import a Bank of America text-selectable PDF for a configured account."""

    initialize_database(paths)
    log_debug(logger, "source_format=boa_pdf parse_start file_name=%s", pdf_path.name)
    try:
        text = extracted_text if extracted_text is not None else extract_pdf_text(pdf_path)
        log_debug(logger, "source_format=boa_pdf text_extracted characters=%s", len(text))
        parsed_rows = parse_boa_pdf_text(text)
        pdf_account_number = extract_boa_pdf_account_number(text)
        statement_start_date, statement_end_date = extract_boa_pdf_statement_period(text)
        log_debug(
            logger,
            "source_format=boa_pdf account_suffix=%s rows_parsed=%s",
            account_number_suffix(pdf_account_number),
            len(parsed_rows),
        )
        return import_boa_transactions(
            paths,
            pdf_path,
            account_id=account_id,
            parsed_rows=parsed_rows,
            source_format="boa_pdf",
            import_label="PDF",
            require_pdf_account_match=True,
            statement_start_date=statement_start_date,
            statement_end_date=statement_end_date,
            pdf_account_number=pdf_account_number,
            logger=logger,
        )
    except ImportFailure as exc:
        record_failed_import(
            paths,
            pdf_path,
            source_format="boa_pdf",
            error_message=str(exc),
            account_id=account_id,
        )
        raise


def import_icici_xls(
    paths: AppPaths,
    xls_path: Path,
    *,
    account_id: int,
    logger: logging.Logger | None = None,
) -> ImportSummary:
    """Import an ICICI Bank old-format Excel statement for a configured account."""

    initialize_database(paths)
    log_debug(logger, "source_format=icici_xls parse_start file_name=%s", xls_path.name)
    try:
        parsed_statement = parse_icici_xls(xls_path)
        log_debug(
            logger,
            "source_format=icici_xls account_suffix=%s rows_parsed=%s",
            account_number_suffix(parsed_statement.account_number),
            len(parsed_statement.transactions),
        )
        return import_parsed_statement(
            paths,
            xls_path,
            account_id=account_id,
            parsed_statement=parsed_statement,
            source_format=ICICI_SOURCE_FORMAT,
            import_label="XLS",
            logger=logger,
        )
    except ImportFailure as exc:
        record_failed_import(
            paths,
            xls_path,
            source_format=ICICI_SOURCE_FORMAT,
            error_message=str(exc),
            account_id=account_id,
        )
        raise


def plan_boa_csv_import(
    paths: AppPaths,
    csv_path: Path,
    *,
    account_id: int,
    logger: logging.Logger | None = None,
) -> ImportPlan:
    """Plan a Bank of America CSV import without writing data or copying files."""

    initialize_database(paths)
    log_debug(logger, "source_format=boa_csv dry_run_parse_start file_name=%s", csv_path.name)
    parsed_rows = parse_boa_csv(csv_path)
    statement_start_date, statement_end_date = statement_period_from_rows(parsed_rows)
    log_debug(
        logger,
        "source_format=boa_csv dry_run_parse_finished rows_parsed=%s",
        len(parsed_rows),
    )
    return plan_boa_transactions(
        paths,
        csv_path,
        account_id=account_id,
        parsed_rows=parsed_rows,
        source_format="boa_csv",
        import_label="CSV",
        require_pdf_account_match=False,
        statement_start_date=statement_start_date,
        statement_end_date=statement_end_date,
        logger=logger,
    )


def plan_boa_pdf_import(
    paths: AppPaths,
    pdf_path: Path,
    *,
    account_id: int,
    extracted_text: str | None = None,
    logger: logging.Logger | None = None,
) -> ImportPlan:
    """Plan a Bank of America PDF import without writing data or copying files."""

    initialize_database(paths)
    log_debug(logger, "source_format=boa_pdf dry_run_parse_start file_name=%s", pdf_path.name)
    text = extracted_text if extracted_text is not None else extract_pdf_text(pdf_path)
    log_debug(logger, "source_format=boa_pdf dry_run_text_extracted characters=%s", len(text))
    parsed_rows = parse_boa_pdf_text(text)
    pdf_account_number = extract_boa_pdf_account_number(text)
    statement_start_date, statement_end_date = extract_boa_pdf_statement_period(text)
    log_debug(
        logger,
        "source_format=boa_pdf dry_run_account_suffix=%s rows_parsed=%s",
        account_number_suffix(pdf_account_number),
        len(parsed_rows),
    )
    return plan_boa_transactions(
        paths,
        pdf_path,
        account_id=account_id,
        parsed_rows=parsed_rows,
        source_format="boa_pdf",
        import_label="PDF",
        require_pdf_account_match=True,
        statement_start_date=statement_start_date,
        statement_end_date=statement_end_date,
        pdf_account_number=pdf_account_number,
        logger=logger,
    )


def plan_icici_xls_import(
    paths: AppPaths,
    xls_path: Path,
    *,
    account_id: int,
    logger: logging.Logger | None = None,
) -> ImportPlan:
    """Plan an ICICI XLS import without writing data or copying files."""

    initialize_database(paths)
    log_debug(
        logger,
        "source_format=icici_xls dry_run_parse_start file_name=%s",
        xls_path.name,
    )
    parsed_statement = parse_icici_xls(xls_path)
    log_debug(
        logger,
        "source_format=icici_xls dry_run_account_suffix=%s rows_parsed=%s",
        account_number_suffix(parsed_statement.account_number),
        len(parsed_statement.transactions),
    )
    return plan_parsed_statement_import(
        paths,
        xls_path,
        account_id=account_id,
        parsed_statement=parsed_statement,
        source_format=ICICI_SOURCE_FORMAT,
        import_label="XLS",
        logger=logger,
    )


def plan_boa_transactions(
    paths: AppPaths,
    import_path: Path,
    *,
    account_id: int,
    parsed_rows: list[ParsedTransaction],
    source_format: str,
    import_label: str,
    require_pdf_account_match: bool,
    statement_start_date: str,
    statement_end_date: str,
    pdf_account_number: str | None = None,
    logger: logging.Logger | None = None,
) -> ImportPlan:
    """Plan parsed Bank of America transactions without persisting changes."""

    file_hash = hash_file(import_path)
    log_debug(
        logger,
        "source_format=%s dry_run_plan_start file_name=%s account_id=%s rows_parsed=%s",
        source_format,
        import_path.name,
        account_id,
        len(parsed_rows),
    )

    with connect_database(paths) as conn:
        account = find_import_account(conn, account_id)
        if account is None:
            raise ImportFailure(f"Account id {account_id} is not configured.")
        configured_account_number = normalize_account_number(account["account_number"])
        validate_boa_import_account(
            account,
            import_label=import_label,
            source_format=source_format,
            configured_account_number=configured_account_number,
            require_pdf_account_match=require_pdf_account_match,
            pdf_account_number=pdf_account_number,
            logger=logger,
        )
        file_metadata = plan_statement_archive_file(
            paths,
            source_path=import_path,
            bank_name=account["bank_name"],
            account_ref=account_number_suffix(configured_account_number),
            statement_start_date=statement_start_date,
            statement_end_date=statement_end_date,
            source_format=source_format,
            file_hash=file_hash,
        )
        rows_already_present = count_duplicate_transaction_hashes(
            conn,
            account_id=account_id,
            parsed_rows=parsed_rows,
            source_format=source_format,
        )

    rows_would_import = len(parsed_rows) - rows_already_present
    log_debug(
        logger,
        "source_format=%s dry_run_rows_parsed=%s rows_would_import=%s "
        "rows_already_present=%s account_suffix=%s",
        source_format,
        len(parsed_rows),
        rows_would_import,
        rows_already_present,
        account_number_suffix(configured_account_number),
    )
    return ImportPlan(
        file_name=import_path.name,
        bank_name="Bank of America",
        account_id=account_id,
        rows_parsed=len(parsed_rows),
        rows_would_import=rows_would_import,
        rows_already_present=rows_already_present,
        canonical_file_name=file_metadata.canonical_file_name,
        processed_path=file_metadata.processed_path,
    )


def plan_parsed_statement_import(
    paths: AppPaths,
    import_path: Path,
    *,
    account_id: int,
    parsed_statement: ParsedStatement,
    source_format: str,
    import_label: str,
    logger: logging.Logger | None = None,
) -> ImportPlan:
    """Plan a parsed statement import without persisting changes."""

    file_hash = hash_file(import_path)
    log_debug(
        logger,
        "source_format=%s dry_run_plan_start file_name=%s account_id=%s rows_parsed=%s",
        source_format,
        import_path.name,
        account_id,
        len(parsed_statement.transactions),
    )

    with connect_database(paths) as conn:
        account = find_import_account(conn, account_id)
        if account is None:
            raise ImportFailure(f"Account id {account_id} is not configured.")
        validate_parsed_statement_account(
            account,
            parsed_statement=parsed_statement,
            import_label=import_label,
            source_format=source_format,
            logger=logger,
        )
        configured_account_number = normalize_account_number(account["account_number"])
        file_metadata = plan_statement_archive_file(
            paths,
            source_path=import_path,
            bank_name=account["bank_name"],
            account_ref=account_number_suffix(configured_account_number),
            statement_start_date=parsed_statement.statement_start_date,
            statement_end_date=parsed_statement.statement_end_date,
            source_format=source_format,
            file_hash=file_hash,
        )
        rows_already_present = count_duplicate_transaction_hashes(
            conn,
            account_id=account_id,
            parsed_rows=parsed_statement.transactions,
            source_format=source_format,
        )

    rows_would_import = len(parsed_statement.transactions) - rows_already_present
    return ImportPlan(
        file_name=import_path.name,
        bank_name=parsed_statement.bank_name,
        account_id=account_id,
        rows_parsed=len(parsed_statement.transactions),
        rows_would_import=rows_would_import,
        rows_already_present=rows_already_present,
        canonical_file_name=file_metadata.canonical_file_name,
        processed_path=file_metadata.processed_path,
        latest_balance_minor_units=parsed_statement.latest_balance_minor_units,
        latest_balance_currency=parsed_statement.currency
        if parsed_statement.latest_balance_minor_units is not None
        else None,
        latest_balance_as_of_date=parsed_statement.latest_balance_as_of_date,
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
    statement_start_date: str,
    statement_end_date: str,
    pdf_account_number: str | None = None,
    logger: logging.Logger | None = None,
) -> ImportSummary:
    """Persist parsed Bank of America transactions for a configured account."""

    file_hash = hash_file(import_path)
    log_debug(
        logger,
        "source_format=%s persistence_start file_name=%s account_id=%s rows_parsed=%s",
        source_format,
        import_path.name,
        account_id,
        len(parsed_rows),
    )

    with connect_database(paths) as conn:
        account = find_import_account(conn, account_id)
        if account is None:
            raise ImportFailure(f"Account id {account_id} is not configured.")
        configured_account_number = normalize_account_number(account["account_number"])
        validate_boa_import_account(
            account,
            import_label=import_label,
            source_format=source_format,
            configured_account_number=configured_account_number,
            require_pdf_account_match=require_pdf_account_match,
            pdf_account_number=pdf_account_number,
            logger=logger,
        )

        bank_id = int(account["bank_id"])
        category_id = uncategorized_category_id(conn)
        file_metadata = archive_statement_file(
            paths,
            source_path=import_path,
            bank_name=account["bank_name"],
            account_ref=account_number_suffix(configured_account_number),
            statement_start_date=statement_start_date,
            statement_end_date=statement_end_date,
            source_format=source_format,
            file_hash=file_hash,
        )
        file_id = ensure_import_file(
            conn,
            file_name=import_path.name,
            file_hash=file_hash,
            bank_id=bank_id,
            metadata=file_metadata,
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
                account_id,
                import_status,
                finished_at,
                rows_parsed,
                rows_imported,
                rows_skipped_duplicate
            ) values (?, ?, ?, ?, current_timestamp, ?, ?, ?)
            """,
            (
                file_id,
                bank_id,
                account_id,
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

    log_debug(
        logger,
        "source_format=%s rows_parsed=%s rows_imported=%s rows_skipped_duplicate=%s "
        "account_suffix=%s",
        source_format,
        len(parsed_rows),
        rows_imported,
        rows_skipped_duplicate,
        account_number_suffix(configured_account_number),
    )
    return ImportSummary(
        file_name=import_path.name,
        bank_name="Bank of America",
        account_id=account_id,
        rows_parsed=len(parsed_rows),
        rows_imported=rows_imported,
        rows_skipped_duplicate=rows_skipped_duplicate,
    )


def import_parsed_statement(
    paths: AppPaths,
    import_path: Path,
    *,
    account_id: int,
    parsed_statement: ParsedStatement,
    source_format: str,
    import_label: str,
    logger: logging.Logger | None = None,
) -> ImportSummary:
    """Persist a parsed statement for a configured account."""

    file_hash = hash_file(import_path)
    log_debug(
        logger,
        "source_format=%s persistence_start file_name=%s account_id=%s rows_parsed=%s",
        source_format,
        import_path.name,
        account_id,
        len(parsed_statement.transactions),
    )

    with connect_database(paths) as conn:
        account = find_import_account(conn, account_id)
        if account is None:
            raise ImportFailure(f"Account id {account_id} is not configured.")
        validate_parsed_statement_account(
            account,
            parsed_statement=parsed_statement,
            import_label=import_label,
            source_format=source_format,
            logger=logger,
        )
        configured_account_number = normalize_account_number(account["account_number"])
        bank_id = int(account["bank_id"])
        category_id = uncategorized_category_id(conn)
        file_metadata = archive_statement_file(
            paths,
            source_path=import_path,
            bank_name=account["bank_name"],
            account_ref=account_number_suffix(configured_account_number),
            statement_start_date=parsed_statement.statement_start_date,
            statement_end_date=parsed_statement.statement_end_date,
            source_format=source_format,
            file_hash=file_hash,
        )
        file_id = ensure_import_file(
            conn,
            file_name=import_path.name,
            file_hash=file_hash,
            bank_id=bank_id,
            metadata=file_metadata,
        )

        rows_imported = 0
        rows_skipped_duplicate = 0
        for parsed in parsed_statement.transactions:
            try:
                conn.execute(
                    """
                    insert into transactions (
                        account_id,
                        category_id,
                        file_id,
                        transaction_date,
                        value_date,
                        amount_minor_units,
                        currency,
                        description,
                        normalized_description,
                        check_number,
                        source_row_key,
                        transaction_hash,
                        transfer_status
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account_id,
                        category_id,
                        file_id,
                        parsed.transaction_date,
                        parsed.value_date,
                        parsed.amount_minor_units,
                        parsed_statement.currency,
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

        update_latest_account_balance(
            conn,
            account_id=account_id,
            parsed_statement=parsed_statement,
            file_id=file_id,
        )
        conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                account_id,
                import_status,
                finished_at,
                rows_parsed,
                rows_imported,
                rows_skipped_duplicate
            ) values (?, ?, ?, ?, current_timestamp, ?, ?, ?)
            """,
            (
                file_id,
                bank_id,
                account_id,
                "success",
                len(parsed_statement.transactions),
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

    log_debug(
        logger,
        "source_format=%s rows_parsed=%s rows_imported=%s rows_skipped_duplicate=%s "
        "account_suffix=%s",
        source_format,
        len(parsed_statement.transactions),
        rows_imported,
        rows_skipped_duplicate,
        account_number_suffix(parsed_statement.account_number),
    )
    return ImportSummary(
        file_name=import_path.name,
        bank_name=parsed_statement.bank_name,
        account_id=account_id,
        rows_parsed=len(parsed_statement.transactions),
        rows_imported=rows_imported,
        rows_skipped_duplicate=rows_skipped_duplicate,
        latest_balance_minor_units=parsed_statement.latest_balance_minor_units,
        latest_balance_currency=parsed_statement.currency
        if parsed_statement.latest_balance_minor_units is not None
        else None,
        latest_balance_as_of_date=parsed_statement.latest_balance_as_of_date,
    )


def validate_parsed_statement_account(
    account: sqlite3.Row,
    *,
    parsed_statement: ParsedStatement,
    import_label: str,
    source_format: str,
    logger: logging.Logger | None,
) -> None:
    """Validate parsed statement metadata against a configured account."""

    configured_account_number = normalize_account_number(account["account_number"])
    statement_account_number = normalize_account_number(parsed_statement.account_number)
    log_debug(
        logger,
        "source_format=%s import_account account_id=%s bank=%s currency=%s "
        "account_suffix=%s statement_suffix=%s",
        source_format,
        account["account_id"],
        account["bank_name"],
        account["currency"],
        account_number_suffix(configured_account_number),
        account_number_suffix(statement_account_number),
    )
    if (
        account["bank_name"] != parsed_statement.bank_name
        or account["currency"] != parsed_statement.currency
    ):
        raise ImportFailure(
            f"{parsed_statement.bank_name} {import_label} import requires a "
            f"{parsed_statement.bank_name} {parsed_statement.currency} account."
        )
    if configured_account_number != statement_account_number:
        raise ImportFailure(
            f"{parsed_statement.bank_name} {import_label} account number does not "
            "match configured account."
        )


def update_latest_account_balance(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    parsed_statement: ParsedStatement,
    file_id: int,
) -> None:
    """Update the account latest balance when a statement is current enough."""

    if (
        parsed_statement.latest_balance_minor_units is None
        or parsed_statement.latest_balance_as_of_date is None
    ):
        return
    conn.execute(
        """
        update accounts
        set latest_balance_minor_units = ?,
            latest_balance_currency = ?,
            latest_balance_as_of_date = ?,
            latest_balance_source_file_id = ?,
            updated_at = current_timestamp
        where account_id = ?
          and (
              latest_balance_as_of_date is null
              or latest_balance_as_of_date <= ?
          )
        """,
        (
            parsed_statement.latest_balance_minor_units,
            parsed_statement.currency,
            parsed_statement.latest_balance_as_of_date,
            file_id,
            account_id,
            parsed_statement.latest_balance_as_of_date,
        ),
    )


def validate_boa_import_account(
    account: sqlite3.Row,
    *,
    import_label: str,
    source_format: str,
    configured_account_number: str,
    require_pdf_account_match: bool,
    pdf_account_number: str | None,
    logger: logging.Logger | None,
) -> None:
    """Validate account metadata for Bank of America import paths."""

    log_debug(
        logger,
        "source_format=%s import_account account_id=%s bank=%s currency=%s "
        "account_suffix=%s",
        source_format,
        account["account_id"],
        account["bank_name"],
        account["currency"],
        account_number_suffix(configured_account_number),
    )
    if account["bank_name"] != "Bank of America" or account["currency"] != "USD":
        raise ImportFailure(
            f"Bank of America {import_label} import requires a "
            "Bank of America USD account."
        )
    if require_pdf_account_match:
        if pdf_account_number != configured_account_number:
            log_debug(
                logger,
                "source_format=%s account_mismatch configured_suffix=%s "
                "statement_suffix=%s",
                source_format,
                account_number_suffix(configured_account_number),
                account_number_suffix(pdf_account_number),
            )
            raise ImportFailure(
                "Bank of America PDF account number does not match configured account."
            )
        log_debug(
            logger,
            "source_format=%s account_match account_suffix=%s",
            source_format,
            account_number_suffix(configured_account_number),
        )


def count_duplicate_transaction_hashes(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    parsed_rows: list[ParsedTransaction],
    source_format: str,
) -> int:
    """Return rows that would violate the account/hash uniqueness constraint."""

    duplicates = 0
    planned_hashes: set[str] = set()
    for parsed in parsed_rows:
        parsed_hash = transaction_hash(parsed, source_format=source_format)
        if parsed_hash in planned_hashes:
            duplicates += 1
            continue
        row = conn.execute(
            """
            select 1
            from transactions
            where account_id = ?
              and transaction_hash = ?
            """,
            (account_id, parsed_hash),
        ).fetchone()
        if row is not None:
            duplicates += 1
        else:
            planned_hashes.add(parsed_hash)
    return duplicates


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


def statement_period_from_rows(
    parsed_rows: list[ParsedTransaction],
) -> tuple[str, str]:
    """Return the inclusive statement period from parsed transaction dates."""

    if not parsed_rows:
        raise ImportFailure("Statement has no parseable transactions.")
    transaction_dates = [row.transaction_date for row in parsed_rows]
    return min(transaction_dates), max(transaction_dates)


def parse_statement_header_date(value: str) -> date:
    """Parse a long-form statement period date."""

    stripped = " ".join(value.strip().split())
    for date_format in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(stripped, date_format).date()
        except ValueError:
            continue
    raise ImportFailure(f"Invalid Bank of America statement period date: {value}")


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


def is_pdf_transaction_continuation(line: str) -> bool:
    """Return whether a PDF text line continues the prior transaction row."""

    return PDF_TRANSACTION_CONTINUATION_PATTERN.match(line) is not None


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
    if source_format == ICICI_SOURCE_FORMAT:
        parts.insert(2, parsed.value_date or "")
    if source_format in {"boa_pdf", ICICI_SOURCE_FORMAT}:
        parts.append(parsed.source_row_key)
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
    metadata: ImportFileMetadata,
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
                original_file_name = ?,
                canonical_file_name = ?,
                source_path = ?,
                processed_path = ?,
                statement_start_date = ?,
                statement_end_date = ?,
                account_ref = ?,
                source_format = ?,
                bank_id = ?,
                updated_at = current_timestamp
            where file_id = ?
            """,
            (
                file_name,
                metadata.original_file_name,
                metadata.canonical_file_name,
                metadata.source_path,
                metadata.processed_path,
                metadata.statement_start_date,
                metadata.statement_end_date,
                metadata.account_ref,
                metadata.source_format,
                bank_id,
                file_id,
            ),
        )
        return file_id

    cursor = conn.execute(
        """
        insert into import_files (
            file_name,
            file_hash,
            bank_id,
            original_file_name,
            canonical_file_name,
            source_path,
            processed_path,
            statement_start_date,
            statement_end_date,
            account_ref,
            source_format
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_name,
            file_hash,
            bank_id,
            metadata.original_file_name,
            metadata.canonical_file_name,
            metadata.source_path,
            metadata.processed_path,
            metadata.statement_start_date,
            metadata.statement_end_date,
            metadata.account_ref,
            metadata.source_format,
        ),
    )
    return int(cursor.lastrowid)


def find_successful_import_by_hash(
    paths: AppPaths,
    file_hash: str,
) -> SuccessfulImportFile | None:
    """Return successful import metadata for an exact file hash match."""

    initialize_database(paths)
    with connect_database(paths) as conn:
        row = conn.execute(
            """
            select
                import_files.file_id,
                import_files.bank_id,
                banks.bank_name,
                import_files.canonical_file_name,
                import_files.processed_path,
                import_files.statement_end_date,
                (
                    select import_attempts.account_id
                    from import_attempts
                    where import_attempts.file_id = import_files.file_id
                      and import_attempts.import_status = 'success'
                    order by import_attempts.attempt_id desc
                    limit 1
                ) as account_id
            from import_files
            left join banks on banks.bank_id = import_files.bank_id
            where import_files.file_hash = ?
              and import_files.last_success_at is not null
            """,
            (file_hash,),
        ).fetchone()

    if row is None:
        return None
    if (
        row["bank_id"] is None
        or row["bank_name"] is None
        or row["canonical_file_name"] is None
        or row["processed_path"] is None
        or row["statement_end_date"] is None
    ):
        return None
    return SuccessfulImportFile(
        file_id=int(row["file_id"]),
        bank_id=int(row["bank_id"]),
        bank_name=row["bank_name"],
        account_id=int(row["account_id"]) if row["account_id"] is not None else None,
        canonical_file_name=row["canonical_file_name"],
        processed_path=row["processed_path"],
        statement_end_date=row["statement_end_date"],
    )


def record_duplicate_import(
    paths: AppPaths,
    duplicate: SuccessfulImportFile,
    *,
    duplicate_path: str,
) -> int:
    """Record an exact duplicate import attempt and return its attempt id."""

    initialize_database(paths)
    with connect_database(paths) as conn:
        cursor = conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                account_id,
                import_status,
                finished_at,
                duplicate_path
            ) values (?, ?, ?, ?, current_timestamp, ?)
            """,
            (
                duplicate.file_id,
                duplicate.bank_id,
                duplicate.account_id,
                "duplicate",
                duplicate_path,
            ),
        )
        conn.execute(
            """
            update import_files
            set updated_at = current_timestamp
            where file_id = ?
            """,
            (duplicate.file_id,),
        )
        conn.commit()
        return int(cursor.lastrowid)


def record_failed_import(
    paths: AppPaths,
    import_path: Path,
    *,
    source_format: str,
    error_message: str,
    account_id: int | None = None,
    bank_id: int | None = None,
    rows_parsed: int = 0,
) -> int:
    """Record a failed supported-file import attempt and return its attempt id."""

    initialize_database(paths)
    file_hash = hash_file(import_path)
    with connect_database(paths) as conn:
        resolved_bank_id = bank_id
        resolved_account_id: int | None = None
        if account_id is not None:
            account = find_import_account(conn, account_id)
            if account is not None:
                resolved_account_id = account_id
                resolved_bank_id = int(account["bank_id"])

        file_id = ensure_import_file_for_attempt(
            conn,
            file_name=import_path.name,
            file_hash=file_hash,
            bank_id=resolved_bank_id,
            source_path=str(import_path.resolve()),
            source_format=source_format,
        )
        cursor = conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                account_id,
                import_status,
                finished_at,
                rows_parsed,
                error_message
            ) values (?, ?, ?, ?, current_timestamp, ?, ?)
            """,
            (
                file_id,
                resolved_bank_id,
                resolved_account_id,
                "failed",
                rows_parsed,
                error_message,
            ),
        )
        conn.execute(
            """
            update import_files
            set updated_at = current_timestamp
            where file_id = ?
            """,
            (file_id,),
        )
        conn.commit()
        return int(cursor.lastrowid)


def ensure_import_file_for_attempt(
    conn: sqlite3.Connection,
    *,
    file_name: str,
    file_hash: str,
    bank_id: int | None,
    source_path: str,
    source_format: str,
) -> int:
    """Return an import file id with enough metadata for retry/history."""

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
                original_file_name = coalesce(original_file_name, ?),
                source_path = ?,
                source_format = ?,
                bank_id = coalesce(?, bank_id),
                updated_at = current_timestamp
            where file_id = ?
            """,
            (
                file_name,
                file_name,
                source_path,
                source_format,
                bank_id,
                file_id,
            ),
        )
        return file_id

    cursor = conn.execute(
        """
        insert into import_files (
            file_name,
            file_hash,
            bank_id,
            original_file_name,
            source_path,
            source_format
        ) values (?, ?, ?, ?, ?, ?)
        """,
        (
            file_name,
            file_hash,
            bank_id,
            file_name,
            source_path,
            source_format,
        ),
    )
    return int(cursor.lastrowid)


def empty_to_none(value: str | None) -> str | None:
    """Normalize empty imported fields to NULL."""

    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def account_number_suffix(value: str | None) -> str:
    """Return the last four digits of an account number for safe diagnostics."""

    normalized = normalize_account_number(value or "")
    return normalized[-4:] if normalized else "(missing)"


def log_debug(logger: logging.Logger | None, message: str, *args: object) -> None:
    """Log importer diagnostics when a CLI runtime logger is available."""

    if logger is not None:
        logger.debug(message, *args)
