"""Statement inventory query helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bankbuddy.accounts import masked_account_number
from bankbuddy.database import connect_database
from bankbuddy.database import initialize_database
from bankbuddy.paths import AppPaths


StatementGroupBy = Literal["year", "month"]


@dataclass(frozen=True)
class StatementSummaryRow:
    """A grouped summary of imported statement files."""

    bank_name: str
    account_id: int
    account_display: str
    year: int
    month: int | None
    file_count: int
    period_start: str
    period_end: str
    rows_imported: int
    rows_skipped_duplicate: int


@dataclass(frozen=True)
class StatementListRow:
    """One imported statement file prepared for CLI display."""

    bank_name: str
    account_id: int
    account_display: str
    period_start: str
    period_end: str
    file_name: str
    processed_path: str | None
    imported_at: str | None
    rows_imported: int
    rows_skipped_duplicate: int

    @property
    def period(self) -> str:
        """Return the inclusive statement period label."""

        return f"{self.period_start} to {self.period_end}"


class StatementFilterError(ValueError):
    """Raised when statement inventory filters cannot be resolved."""


def statement_summary(
    paths: AppPaths,
    *,
    group_by: StatementGroupBy = "year",
    bank_name: str | None = None,
    account_id: int | None = None,
    account_last4: str | None = None,
    years: list[int] | None = None,
) -> list[StatementSummaryRow]:
    """Return statement file counts grouped by statement end year or month."""

    if group_by not in {"year", "month"}:
        raise StatementFilterError("Statement summary can group by year or month.")
    selected_account_id = resolve_selected_account_id(
        paths,
        account_id=account_id,
        account_last4=account_last4,
    )
    conditions, parameters = statement_filter_conditions(
        bank_name=bank_name,
        account_id=selected_account_id,
        years=years,
    )
    month_expression = (
        "cast(substr(import_files.statement_end_date, 6, 2) as integer)"
        if group_by == "month"
        else "null"
    )
    group_columns = [
        "banks.bank_name",
        "accounts.account_id",
        "accounts.account_number",
        "accounts.display_name",
        "statement_year",
    ]
    if group_by == "month":
        group_columns.append("statement_month")

    initialize_database(paths)
    with connect_database(paths) as conn:
        rows = conn.execute(
            f"""
            with representative_attempts as (
                select min(attempt_id) as attempt_id
                from import_attempts
                where import_status = 'success'
                  and account_id is not null
                group by file_id, account_id
            )
            select
                banks.bank_name,
                accounts.account_id,
                accounts.account_number,
                accounts.display_name,
                cast(substr(import_files.statement_end_date, 1, 4) as integer)
                    as statement_year,
                {month_expression} as statement_month,
                count(import_files.file_id) as file_count,
                min(import_files.statement_start_date) as period_start,
                max(import_files.statement_end_date) as period_end,
                sum(import_attempts.rows_imported) as rows_imported,
                sum(import_attempts.rows_skipped_duplicate)
                    as rows_skipped_duplicate
            from representative_attempts
            join import_attempts using (attempt_id)
            join import_files using (file_id)
            join accounts on accounts.account_id = import_attempts.account_id
            join banks on banks.bank_id = accounts.bank_id
            where {' and '.join(conditions)}
            group by {', '.join(group_columns)}
            order by
                banks.bank_name,
                accounts.account_id,
                statement_year,
                statement_month
            """,
            parameters,
        ).fetchall()

    return [
        StatementSummaryRow(
            bank_name=row["bank_name"],
            account_id=int(row["account_id"]),
            account_display=account_display(row),
            year=int(row["statement_year"]),
            month=(
                int(row["statement_month"])
                if row["statement_month"] is not None
                else None
            ),
            file_count=int(row["file_count"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            rows_imported=int(row["rows_imported"]),
            rows_skipped_duplicate=int(row["rows_skipped_duplicate"]),
        )
        for row in rows
    ]


def list_statement_files(
    paths: AppPaths,
    *,
    bank_name: str | None = None,
    account_id: int | None = None,
    account_last4: str | None = None,
    year: int | None = None,
) -> list[StatementListRow]:
    """Return one row per successfully imported statement file."""

    selected_account_id = resolve_selected_account_id(
        paths,
        account_id=account_id,
        account_last4=account_last4,
    )
    conditions, parameters = statement_filter_conditions(
        bank_name=bank_name,
        account_id=selected_account_id,
        years=[year] if year is not None else None,
    )

    initialize_database(paths)
    with connect_database(paths) as conn:
        rows = conn.execute(
            f"""
            with representative_attempts as (
                select min(attempt_id) as attempt_id
                from import_attempts
                where import_status = 'success'
                  and account_id is not null
                group by file_id, account_id
            )
            select
                banks.bank_name,
                accounts.account_id,
                accounts.account_number,
                accounts.display_name,
                import_files.statement_start_date,
                import_files.statement_end_date,
                coalesce(
                    import_files.canonical_file_name,
                    import_files.file_name
                ) as file_name,
                import_files.processed_path,
                import_attempts.finished_at,
                import_attempts.rows_imported,
                import_attempts.rows_skipped_duplicate
            from representative_attempts
            join import_attempts using (attempt_id)
            join import_files using (file_id)
            join accounts on accounts.account_id = import_attempts.account_id
            join banks on banks.bank_id = accounts.bank_id
            where {' and '.join(conditions)}
            order by
                banks.bank_name,
                accounts.account_id,
                import_files.statement_start_date,
                import_files.statement_end_date,
                import_files.file_id
            """,
            parameters,
        ).fetchall()

    return [
        StatementListRow(
            bank_name=row["bank_name"],
            account_id=int(row["account_id"]),
            account_display=account_display(row),
            period_start=row["statement_start_date"],
            period_end=row["statement_end_date"],
            file_name=row["file_name"],
            processed_path=row["processed_path"],
            imported_at=row["finished_at"],
            rows_imported=int(row["rows_imported"]),
            rows_skipped_duplicate=int(row["rows_skipped_duplicate"]),
        )
        for row in rows
    ]


def statement_filter_conditions(
    *,
    bank_name: str | None,
    account_id: int | None,
    years: list[int] | None,
) -> tuple[list[str], list[object]]:
    """Build common statement metadata filters."""

    conditions = [
        "import_files.statement_start_date is not null",
        "import_files.statement_end_date is not null",
    ]
    parameters: list[object] = []
    if bank_name is not None:
        normalized_bank_name = bank_name.strip()
        if not normalized_bank_name:
            raise StatementFilterError("Bank name must not be empty.")
        conditions.append("lower(banks.bank_name) = lower(?)")
        parameters.append(normalized_bank_name)
    if account_id is not None:
        conditions.append("accounts.account_id = ?")
        parameters.append(account_id)
    if years:
        placeholders = ", ".join("?" for _year in years)
        conditions.append(
            "cast(substr(import_files.statement_end_date, 1, 4) as integer) "
            f"in ({placeholders})"
        )
        parameters.extend(years)
    return conditions, parameters


def resolve_selected_account_id(
    paths: AppPaths,
    *,
    account_id: int | None,
    account_last4: str | None,
) -> int | None:
    """Resolve account selectors to a single account id, if requested."""

    if account_id is not None and account_last4 is not None:
        raise StatementFilterError(
            "--account-id cannot be combined with --account-last4."
        )
    if account_last4 is None:
        return account_id

    suffix = normalize_account_digits(account_last4)
    if len(suffix) != 4:
        raise StatementFilterError(
            "Account last four digits must contain exactly four digits."
        )

    with connect_database(paths) as conn:
        rows = conn.execute(
            """
            select account_id, account_number
            from accounts
            order by account_id
            """
        ).fetchall()

    matches = [
        int(row["account_id"])
        for row in rows
        if normalize_account_digits(row["account_number"]).endswith(suffix)
    ]
    if not matches:
        raise StatementFilterError(f"No account matches last four digits: {suffix}.")
    if len(matches) > 1:
        raise StatementFilterError(
            "Account last four digits are ambiguous: "
            f"{suffix}. Use --account-id."
        )
    return matches[0]


def account_display(row) -> str:
    """Return the display name or masked account number for a query row."""

    return row["display_name"] or masked_account_number(row["account_number"])


def normalize_account_digits(value: str) -> str:
    """Return only digits from an account selector."""

    return "".join(char for char in value if char.isdigit())
