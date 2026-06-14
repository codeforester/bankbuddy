"""Read-only data quality audits for imported statements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from datetime import timedelta

from bankbuddy.accounts import masked_account_number
from bankbuddy.database import connect_database
from bankbuddy.database import initialize_database
from bankbuddy.paths import AppPaths


@dataclass(frozen=True)
class AuditFinding:
    """One statement coverage finding in an audit window."""

    status: str
    period_start: date
    period_end: date
    file_name: str | None


@dataclass(frozen=True)
class AccountStatementAudit:
    """Statement coverage findings for one account and one audit window."""

    account_id: int
    account_display: str
    bank_name: str
    window_start: date
    window_end: date
    findings: list[AuditFinding]


@dataclass(frozen=True)
class AccountSummary:
    """A configured account available for audit."""

    account_id: int
    account_display: str
    bank_name: str


@dataclass(frozen=True)
class StatementPeriod:
    """Imported statement period metadata."""

    file_id: int
    account_id: int
    period_start: date
    period_end: date
    file_name: str


class AuditFilterError(ValueError):
    """Raised when audit selector options cannot be resolved."""


def audit_statement_coverage(
    paths: AppPaths,
    *,
    account_id: int | None = None,
    account_last4: str | None = None,
    years: list[int] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[AccountStatementAudit]:
    """Audit imported statement periods for selected accounts and windows."""

    initialize_database(paths)
    validate_date_selectors(years=years, date_from=date_from, date_to=date_to)
    selected_account_id = resolve_selected_account_id(
        paths,
        account_id=account_id,
        account_last4=account_last4,
    )
    accounts = list_auditable_accounts(paths, account_id=selected_account_id)
    periods_by_account = statement_periods_by_account(paths, account_id=selected_account_id)

    audits: list[AccountStatementAudit] = []
    for account in accounts:
        account_periods = periods_by_account.get(account.account_id, [])
        windows = audit_windows(
            periods=account_periods,
            years=years,
            date_from=date_from,
            date_to=date_to,
        )
        for window_start, window_end in windows:
            audits.append(
                AccountStatementAudit(
                    account_id=account.account_id,
                    account_display=account.account_display,
                    bank_name=account.bank_name,
                    window_start=window_start,
                    window_end=window_end,
                    findings=analyze_statement_periods(
                        account_periods,
                        window_start=window_start,
                        window_end=window_end,
                    ),
                )
            )
    return audits


def validate_date_selectors(
    *,
    years: list[int] | None,
    date_from: str | None,
    date_to: str | None,
) -> None:
    """Validate mutually exclusive audit date selectors."""

    if years and (date_from or date_to):
        raise AuditFilterError("--years cannot be combined with --from or --to.")
    if (date_from is None) != (date_to is None):
        raise AuditFilterError("--from and --to must be provided together.")
    if date_from is not None and parse_iso_date(date_from) > parse_iso_date(date_to or ""):
        raise AuditFilterError("--from must be on or before --to.")


def resolve_selected_account_id(
    paths: AppPaths,
    *,
    account_id: int | None,
    account_last4: str | None,
) -> int | None:
    """Resolve account selectors to a single account id, if requested."""

    if account_id is not None and account_last4 is not None:
        raise AuditFilterError("--account-id cannot be combined with --account-last4.")
    if account_last4 is None:
        return account_id

    suffix = normalize_account_digits(account_last4)
    if len(suffix) != 4:
        raise AuditFilterError(
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
        raise AuditFilterError(f"No account matches last four digits: {suffix}.")
    if len(matches) > 1:
        raise AuditFilterError(
            "Account last four digits are ambiguous: "
            f"{suffix}. Use --account-id."
        )
    return matches[0]


def list_auditable_accounts(
    paths: AppPaths,
    *,
    account_id: int | None,
) -> list[AccountSummary]:
    """Return configured accounts selected for audit."""

    conditions: list[str] = []
    parameters: list[object] = []
    if account_id is not None:
        conditions.append("accounts.account_id = ?")
        parameters.append(account_id)
    where_clause = f"where {' and '.join(conditions)}" if conditions else ""

    with connect_database(paths) as conn:
        rows = conn.execute(
            f"""
            select
                accounts.account_id,
                accounts.account_number,
                accounts.display_name,
                banks.bank_name
            from accounts
            join banks using (bank_id)
            {where_clause}
            order by banks.bank_name, accounts.account_id
            """,
            parameters,
        ).fetchall()

    return [
        AccountSummary(
            account_id=int(row["account_id"]),
            account_display=row["display_name"]
            or masked_account_number(row["account_number"]),
            bank_name=row["bank_name"],
        )
        for row in rows
    ]


def statement_periods_by_account(
    paths: AppPaths,
    *,
    account_id: int | None,
) -> dict[int, list[StatementPeriod]]:
    """Return successful imported statement periods keyed by account id."""

    conditions = [
        "import_attempts.import_status = 'success'",
        "import_attempts.account_id is not null",
        "import_files.statement_start_date is not null",
        "import_files.statement_end_date is not null",
    ]
    parameters: list[object] = []
    if account_id is not None:
        conditions.append("import_attempts.account_id = ?")
        parameters.append(account_id)

    with connect_database(paths) as conn:
        rows = conn.execute(
            f"""
            select distinct
                import_files.file_id,
                import_attempts.account_id,
                import_files.statement_start_date,
                import_files.statement_end_date,
                coalesce(import_files.canonical_file_name, import_files.file_name) as file_name
            from import_attempts
            join import_files using (file_id)
            where {' and '.join(conditions)}
            order by
                import_attempts.account_id,
                import_files.statement_start_date,
                import_files.statement_end_date,
                import_files.file_id
            """,
            parameters,
        ).fetchall()

    periods_by_account: dict[int, list[StatementPeriod]] = {}
    for row in rows:
        period = StatementPeriod(
            file_id=int(row["file_id"]),
            account_id=int(row["account_id"]),
            period_start=parse_iso_date(row["statement_start_date"]),
            period_end=parse_iso_date(row["statement_end_date"]),
            file_name=row["file_name"],
        )
        periods_by_account.setdefault(period.account_id, []).append(period)
    return periods_by_account


def audit_windows(
    *,
    periods: list[StatementPeriod],
    years: list[int] | None,
    date_from: str | None,
    date_to: str | None,
) -> list[tuple[date, date]]:
    """Return audit windows for one account."""

    if years:
        return [
            (date(year, 1, 1), date(year, 12, 31))
            for year in sorted(set(years))
        ]
    if date_from is not None and date_to is not None:
        return [(parse_iso_date(date_from), parse_iso_date(date_to))]
    if not periods:
        return []
    return [
        (
            min(period.period_start for period in periods),
            max(period.period_end for period in periods),
        )
    ]


def analyze_statement_periods(
    periods: list[StatementPeriod],
    *,
    window_start: date,
    window_end: date,
) -> list[AuditFinding]:
    """Analyze imported statement periods within one inclusive audit window."""

    relevant_periods = [
        period
        for period in periods
        if period.period_end >= window_start and period.period_start <= window_end
    ]
    findings: list[AuditFinding] = []
    cursor = window_start - timedelta(days=1)
    seen_periods: set[tuple[date, date]] = set()

    for period in relevant_periods:
        period_key = (period.period_start, period.period_end)
        clipped_start = max(period.period_start, window_start)
        clipped_end = min(period.period_end, window_end)
        if period_key in seen_periods:
            findings.append(
                AuditFinding("duplicate", clipped_start, clipped_end, period.file_name)
            )
            continue
        seen_periods.add(period_key)

        next_uncovered = cursor + timedelta(days=1)
        if clipped_start > next_uncovered:
            findings.append(
                AuditFinding(
                    "missing",
                    next_uncovered,
                    clipped_start - timedelta(days=1),
                    None,
                )
            )

        if clipped_start <= cursor:
            findings.append(
                AuditFinding(
                    "overlap",
                    clipped_start,
                    min(clipped_end, cursor),
                    period.file_name,
                )
            )
            covered_start = cursor + timedelta(days=1)
            if covered_start <= clipped_end:
                findings.append(
                    AuditFinding(
                        "covered",
                        covered_start,
                        clipped_end,
                        period.file_name,
                    )
                )
        else:
            findings.append(
                AuditFinding("covered", clipped_start, clipped_end, period.file_name)
            )

        cursor = max(cursor, clipped_end)

    if cursor < window_end:
        findings.append(
            AuditFinding(
                "missing",
                cursor + timedelta(days=1),
                window_end,
                None,
            )
        )

    return findings


def parse_iso_date(value: str) -> date:
    """Parse an ISO date string."""

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AuditFilterError(f"Invalid date: {value}. Expected YYYY-MM-DD.") from exc


def normalize_account_digits(value: str) -> str:
    """Return only digits from an account selector."""

    return "".join(char for char in value if char.isdigit())
