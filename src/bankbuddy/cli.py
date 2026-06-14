"""Command line interface for BankBuddy."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import io
from pathlib import Path
from typing import Callable
from typing import Literal

import click

from bankbuddy import __version__
from bankbuddy.accounts import AccountAlreadyExistsError
from bankbuddy.accounts import add_account
from bankbuddy.accounts import list_accounts
from bankbuddy.accounts import masked_account_number
from bankbuddy.database import initialize_database
from bankbuddy.exports import ExportFailure
from bankbuddy.exports import export_sqlite_database
from bankbuddy.import_history import list_import_history
from bankbuddy.import_retry import RetryFailure
from bankbuddy.import_retry import retry_import_attempt
from bankbuddy.inbox import import_inbox
from bankbuddy.imports import ImportFailure
from bankbuddy.imports import ImportPlan
from bankbuddy.imports import ImportSummary
from bankbuddy.imports import import_boa_csv
from bankbuddy.imports import import_boa_pdf
from bankbuddy.imports import plan_boa_csv_import
from bankbuddy.imports import plan_boa_pdf_import
from bankbuddy.paths import resolve_app_paths
from bankbuddy.reports import spending_report
from bankbuddy.runtime import CliRuntime
from bankbuddy.runtime import RuntimeConfigError
from bankbuddy.runtime import create_runtime
from bankbuddy.transactions import format_minor_units
from bankbuddy.transactions import list_transactions
from bankbuddy.transactions import summarize_transactions
from bankbuddy.transactions import TransactionFilterError
from bankbuddy.transactions import TransactionRow
from bankbuddy.transactions import TransactionSortError


ColumnAlign = Literal["left", "right"]
OutputFormat = Literal["pretty", "csv", "tsv"]


@dataclass(frozen=True)
class TransactionColumn:
    """Display and machine-output metadata for one transaction column."""

    header: str
    machine_header: str
    align: ColumnAlign
    value: Callable[[TransactionRow], str]


@click.group(
    name="bankbuddy",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="bankbuddy")
@click.option(
    "-v",
    "--debug",
    is_flag=True,
    help="Enable DEBUG logging on the user-facing stream.",
)
@click.option("--environment", help="Set the BankBuddy environment for this command.")
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False),
    help="Load an additional config file.",
)
@click.option("--keep-temp", is_flag=True, help="Preserve this run's temp directory.")
@click.option(
    "--log-file",
    type=click.Path(dir_okay=False),
    help="Override the persistent log file.",
)
@click.pass_context
def main(
    ctx: click.Context,
    debug: bool,
    environment: str | None,
    config_path: str | None,
    keep_temp: bool,
    log_file: str | None,
) -> None:
    """Local-first personal finance tracking."""

    try:
        runtime = create_runtime(
            debug=debug,
            environment=environment,
            config_path=config_path,
            keep_temp=keep_temp,
            log_file=log_file,
        )
    except (OSError, RuntimeConfigError) as exc:
        raise click.ClickException(str(exc)) from exc

    ctx.obj = runtime
    ctx.call_on_close(runtime.cleanup)


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show the local BankBuddy app state."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    initialized = "yes" if paths.database.exists() else "no"
    runtime.log.debug(
        "status environment=%s data_home=%s database=%s initialized=%s",
        paths.environment,
        paths.root,
        paths.database,
        initialized,
    )

    click.echo(f"Environment: {paths.environment}")
    click.echo(f"Data home: {paths.root}")
    click.echo(f"Database: {paths.database}")
    click.echo(f"Initialized: {initialized}")


@main.command("init")
@click.pass_context
def init_command(ctx: click.Context) -> None:
    """Initialize the local BankBuddy app directory and database."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    initialize_database(paths)
    runtime.log.debug("init home=%s database=%s", paths.root, paths.database)
    click.echo(f"Initialized Bank Buddy at {paths.root}")


@main.group()
def account() -> None:
    """Manage configured bank accounts."""


@account.command("add")
@click.option("--bank", "bank_name", required=True, help="Bank name.")
@click.option("--country", required=True, help="Bank country code or name.")
@click.option("--account-number", required=True, help="Actual account number.")
@click.option(
    "--type",
    "account_type",
    required=True,
    type=click.Choice(
        ["checking", "savings", "cd", "credit_card", "investment"],
        case_sensitive=False,
    ),
    help="Account type.",
)
@click.option(
    "--currency",
    required=True,
    type=click.Choice(["USD", "INR"], case_sensitive=False),
    help="Account currency.",
)
@click.option(
    "--statement-ref",
    "statement_account_ref",
    help="Optional parser-visible account reference, such as last four digits.",
)
@click.option("--display-name", help="Optional friendly account label.")
@click.pass_context
def account_add(
    ctx: click.Context,
    bank_name: str,
    country: str,
    account_number: str,
    account_type: str,
    currency: str,
    statement_account_ref: str | None,
    display_name: str | None,
) -> None:
    """Add a bank account."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        account = add_account(
            paths,
            bank_name=bank_name,
            country=country,
            account_number=account_number,
            account_type=account_type,
            currency=currency,
            statement_account_ref=statement_account_ref,
            display_name=display_name,
        )
    except AccountAlreadyExistsError as exc:
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug(
        "account_added account_id=%s bank=%s country=%s type=%s currency=%s "
        "account_suffix=%s",
        account.account_id,
        account.bank_name,
        account.country,
        account.account_type,
        account.currency,
        account.account_number[-4:],
    )
    click.echo(f"Added account {account.account_id} for {account.bank_name}")


@account.command("list")
@click.pass_context
def account_list(ctx: click.Context) -> None:
    """List configured bank accounts."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    accounts = list_accounts(paths)
    runtime.log.debug("account_list count=%s", len(accounts))
    if not accounts:
        click.echo("No accounts configured.")
        return

    click.echo("ID  Bank  Name  Type  Currency  Account")
    for account in accounts:
        name = account.display_name or "-"
        click.echo(
            f"{account.account_id}  {account.bank_name}  {name}  "
            f"{account.account_type}  {account.currency}  "
            f"{masked_account_number(account.account_number)}"
        )


@main.group()
def tx() -> None:
    """Inspect imported transactions."""


@tx.command("list")
@click.option("--account-id", type=int, help="Filter by configured account id.")
@click.option("--bank", "bank_name", help="Filter by exact bank name.")
@click.option("--currency", help="Filter by transaction currency.")
@click.option("--account-number", help="Filter by actual account number.")
@click.option(
    "--account-last4",
    help="Filter by unambiguous account-number suffix.",
)
@click.option("--from", "date_from", help="Inclusive start date, YYYY-MM-DD.")
@click.option("--to", "date_to", help="Inclusive end date, YYYY-MM-DD.")
@click.option(
    "--direction",
    type=click.Choice(["debit", "credit"], case_sensitive=False),
    help="Filter by money direction: debit for negative amounts, credit for positive.",
)
@click.option("--sort", "sort_expression", help="Comma-separated sort fields.")
@click.option(
    "--order",
    type=click.Choice(["asc", "desc"], case_sensitive=False),
    default="asc",
    show_default=True,
    help="Default sort direction for fields without an explicit direction.",
)
@click.option(
    "--view",
    type=click.Choice(["default", "compact", "ledger"], case_sensitive=False),
    default="default",
    show_default=True,
    help="Transaction list view.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["pretty", "csv", "tsv"], case_sensitive=False),
    default="pretty",
    show_default=True,
    help="Transaction output format.",
)
@click.option("--summary", is_flag=True, help="Show summary totals for listed rows.")
@click.pass_context
def tx_list(
    ctx: click.Context,
    account_id: int | None,
    bank_name: str | None,
    currency: str | None,
    account_number: str | None,
    account_last4: str | None,
    date_from: str | None,
    date_to: str | None,
    direction: str | None,
    sort_expression: str | None,
    order: str,
    view: str,
    output_format: str,
    summary: bool,
) -> None:
    """List imported transactions."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    normalized_date_from = validate_iso_date(date_from, "--from")
    normalized_date_to = validate_iso_date(date_to, "--to")
    try:
        rows = list_transactions(
            paths,
            account_id=account_id,
            bank_name=bank_name,
            currency=currency,
            account_number=account_number,
            account_last4=account_last4,
            date_from=normalized_date_from,
            date_to=normalized_date_to,
            direction=direction.lower() if direction else None,
            sort=sort_expression,
            default_order=order.lower(),
        )
    except (TransactionFilterError, TransactionSortError) as exc:
        raise click.ClickException(str(exc)) from exc

    normalized_view = view.lower()
    normalized_format = output_format.lower()
    if summary and normalized_format != "pretty":
        raise click.ClickException(
            "--summary is only supported with --format pretty."
        )

    runtime.log.debug(
        "tx_list count=%s account_id=%s bank=%s currency=%s "
        "account_number_suffix=%s account_last4=%s date_from=%s date_to=%s "
        "direction=%s sort=%s order=%s view=%s format=%s summary=%s",
        len(rows),
        account_id,
        bank_name,
        currency,
        account_number_suffix(account_number),
        account_number_suffix(account_last4),
        normalized_date_from,
        normalized_date_to,
        direction,
        sort_expression,
        order,
        normalized_view,
        normalized_format,
        summary,
    )
    if not rows:
        if normalized_format in {"csv", "tsv"}:
            render_transaction_rows(
                rows,
                view=normalized_view,
                output_format=normalized_format,
            )
            return
        click.echo("No transactions found.")
        return

    render_transaction_rows(
        rows,
        view=normalized_view,
        output_format=normalized_format,
    )
    if summary:
        click.echo("")
        render_transaction_summary(rows)


def account_number_suffix(account_number: str | None) -> str | None:
    """Return a display-safe suffix for logging account filters."""

    if account_number is None:
        return None
    digits = "".join(char for char in account_number if char.isdigit())
    if not digits:
        return ""
    return digits[-4:]


def render_transaction_rows(
    rows: list[TransactionRow],
    *,
    view: str,
    output_format: str,
) -> None:
    """Render transaction rows for a view and output format."""

    columns = transaction_columns(view)
    if output_format == "pretty":
        render_pretty_rows(rows, columns)
        return

    if output_format == "csv":
        render_delimited_rows(rows, columns, delimiter=",")
        return

    render_delimited_rows(rows, columns, delimiter="\t")


def transaction_columns(view: str) -> list[TransactionColumn]:
    """Return the transaction columns selected by a named view."""

    columns = {
        "id": TransactionColumn(
            "ID",
            "id",
            "right",
            lambda row: str(row.transaction_id),
        ),
        "date": TransactionColumn(
            "Date",
            "date",
            "left",
            lambda row: row.transaction_date,
        ),
        "account": TransactionColumn(
            "Account",
            "account",
            "left",
            lambda row: row.account_display,
        ),
        "type": TransactionColumn(
            "Type",
            "type",
            "left",
            transaction_type,
        ),
        "amount": TransactionColumn(
            "Amount",
            "amount",
            "right",
            lambda row: format_minor_units(row.amount_minor_units),
        ),
        "currency": TransactionColumn(
            "Currency",
            "currency",
            "left",
            lambda row: row.currency,
        ),
        "description": TransactionColumn(
            "Description",
            "description",
            "left",
            lambda row: row.description,
        ),
    }

    if view == "compact":
        return [
            columns["date"],
            columns["amount"],
            columns["currency"],
            columns["description"],
        ]
    if view == "ledger":
        return [
            columns["id"],
            columns["date"],
            columns["account"],
            columns["type"],
            columns["amount"],
            columns["currency"],
            columns["description"],
        ]
    return [
        columns["id"],
        columns["date"],
        columns["account"],
        columns["amount"],
        columns["currency"],
        columns["description"],
    ]


def render_pretty_rows(
    rows: list[TransactionRow],
    columns: list[TransactionColumn],
) -> None:
    """Render transaction rows as an aligned table."""

    values = [[column.value(row) for column in columns] for row in rows]
    widths = [
        max(
            [len(column.header)]
            + [len(row_values[index]) for row_values in values]
        )
        for index, column in enumerate(columns)
    ]

    click.echo(format_pretty_row(
        [column.header for column in columns],
        widths,
        [column.align for column in columns],
    ))
    click.echo("-+-".join("-" * width for width in widths))
    for row_values in values:
        click.echo(format_pretty_row(
            row_values,
            widths,
            [column.align for column in columns],
        ))


def format_pretty_row(
    values: list[str],
    widths: list[int],
    aligns: list[ColumnAlign],
) -> str:
    """Format one aligned pretty-table row."""

    cells = []
    for value, width, align in zip(values, widths, aligns):
        if align == "right":
            cells.append(value.rjust(width))
        else:
            cells.append(value.ljust(width))
    return " | ".join(cells)


def render_delimited_rows(
    rows: list[TransactionRow],
    columns: list[TransactionColumn],
    *,
    delimiter: str,
) -> None:
    """Render transaction rows as CSV or TSV."""

    output = io.StringIO()
    writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
    writer.writerow([column.machine_header for column in columns])
    for row in rows:
        writer.writerow([column.value(row) for column in columns])
    click.echo(output.getvalue(), nl=False)


def render_transaction_summary(rows: list[TransactionRow]) -> None:
    """Render per-currency summary totals for transaction rows."""

    click.echo("Summary")
    click.echo("Currency  Transactions  Debits  Credits  Net")
    for row in summarize_transactions(rows):
        click.echo(
            f"{row.currency}  {row.transaction_count}  "
            f"{format_minor_units(row.debit_minor_units)}  "
            f"{format_minor_units(row.credit_minor_units)}  "
            f"{format_minor_units(row.net_minor_units)}"
        )


def transaction_type(row: TransactionRow) -> str:
    """Return a simple debit/credit/zero label for a transaction row."""

    if row.amount_minor_units < 0:
        return "debit"
    if row.amount_minor_units > 0:
        return "credit"
    return "zero"


def validate_iso_date(value: str | None, option_name: str) -> str | None:
    """Validate a CLI date option as YYYY-MM-DD."""

    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise click.ClickException(
            f"Invalid date for {option_name}: {value}. Expected YYYY-MM-DD."
        ) from exc


@main.group()
def report() -> None:
    """Show financial reports."""


@report.command("spending")
@click.option(
    "--year",
    required=True,
    type=click.IntRange(min=1900, max=9999),
    help="Report year.",
)
@click.option(
    "--month",
    type=click.IntRange(min=1, max=12),
    help="Optional report month.",
)
@click.pass_context
def report_spending(
    ctx: click.Context,
    year: int,
    month: int | None,
) -> None:
    """Summarize outgoing spending by category."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    rows = spending_report(paths, year=year, month=month)
    runtime.log.debug(
        "report_spending count=%s year=%s month=%s",
        len(rows),
        year,
        month,
    )
    period_label = f"{year:04d}-{month:02d}" if month is not None else f"{year:04d}"
    if not rows:
        click.echo(f"No spending found for {period_label}.")
        return

    click.echo("Category  Currency  Transactions  Spending")
    for row in rows:
        click.echo(
            f"{row.category_name}  {row.currency}  {row.transaction_count}  "
            f"{format_minor_units(row.spending_minor_units)}"
        )


@main.group("export")
def export_command() -> None:
    """Export local BankBuddy data."""


@export_command.command("sqlite")
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="SQLite export destination.",
)
@click.option("--force", is_flag=True, help="Overwrite an existing output file.")
@click.pass_context
def export_sqlite_command(
    ctx: click.Context,
    output_path: Path,
    force: bool,
) -> None:
    """Export the local SQLite database."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        exported_path = export_sqlite_database(paths, output_path, force=force)
    except ExportFailure as exc:
        runtime.log.debug("export_sqlite_failed reason=%s", exc)
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug("export_sqlite output=%s force=%s", exported_path, force)
    click.echo(f"Exported SQLite database to {exported_path}")
    click.echo(
        "Warning: export contains sensitive financial data and actual account numbers."
    )


@main.group("import", invoke_without_command=True, no_args_is_help=False)
@click.option(
    "--file",
    "file_path",
    required=False,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Statement file to import.",
)
@click.option("--account-id", type=int, help="Configured account id.")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview import actions without changing the database or files.",
)
@click.pass_context
def import_command(
    ctx: click.Context,
    file_path: Path | None,
    account_id: int | None,
    dry_run: bool,
) -> None:
    """Import statements or inspect import history."""

    if ctx.invoked_subcommand is not None:
        return
    if file_path is None or account_id is None:
        raise click.ClickException("Import requires --file and --account-id.")

    run_statement_import(ctx, file_path, account_id, dry_run=dry_run)


@import_command.command("history")
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=20,
    show_default=True,
    help="Maximum number of attempts to show.",
)
@click.option(
    "--status",
    type=click.Choice(
        ["success", "failed", "partial", "duplicate"],
        case_sensitive=False,
    ),
    help="Filter by import status.",
)
@click.pass_context
def import_history_command(
    ctx: click.Context,
    limit: int,
    status: str | None,
) -> None:
    """List prior import attempts."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    normalized_status = status.lower() if status else None
    rows = list_import_history(paths, status=normalized_status, limit=limit)
    runtime.log.debug(
        "import_history count=%s status=%s limit=%s",
        len(rows),
        normalized_status,
        limit,
    )
    if not rows:
        click.echo("No import attempts found.")
        return

    click.echo(
        "ID  File  Canonical  Processed  Duplicate  Bank  Account  Status  "
        "Started  Finished  Parsed  Imported  Duplicates  Error"
    )
    for row in rows:
        account = str(row.account_id) if row.account_id is not None else "-"
        click.echo(
            f"{row.attempt_id}  {row.file_name}  {row.canonical_file_name}  "
            f"{row.processed_path or '-'}  {row.duplicate_path or '-'}  "
            f"{row.bank_name}  {account}  {row.status}  {row.started_at}  "
            f"{row.finished_at or '-'}  {row.rows_parsed}  "
            f"{row.rows_imported}  {row.rows_skipped_duplicate}  "
            f"{row.error_message or '-'}"
        )


@import_command.command("retry")
@click.argument("attempt_id", type=click.IntRange(min=1))
@click.option(
    "--account-id",
    type=int,
    help="Account id override for failed attempts that did not store an account.",
)
@click.pass_context
def import_retry_command(
    ctx: click.Context,
    attempt_id: int,
    account_id: int | None,
) -> None:
    """Retry a failed import attempt."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        summary = retry_import_attempt(
            paths,
            attempt_id,
            account_id=account_id,
            logger=runtime.log,
        )
    except (ImportFailure, RetryFailure) as exc:
        runtime.log.debug("import_retry_failed attempt_id=%s reason=%s", attempt_id, exc)
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug(
        "import_retry_finished attempt_id=%s file_name=%s rows_parsed=%s "
        "rows_imported=%s rows_skipped_duplicate=%s",
        attempt_id,
        summary.file_name,
        summary.rows_parsed,
        summary.rows_imported,
        summary.rows_skipped_duplicate,
    )
    click.echo(f"Retried attempt: {attempt_id}")
    print_import_summary(summary)


@import_command.command("inbox")
@click.option(
    "--account-id",
    type=int,
    help="Configured account id. Required for CSV files; optional for routable PDFs.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview inbox import actions without changing the database or files.",
)
@click.pass_context
def import_inbox_command(
    ctx: click.Context,
    account_id: int | None,
    dry_run: bool,
) -> None:
    """Import supported files from the managed inbox."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    dry_run = dry_run or import_dry_run_from_context(ctx)
    summary = import_inbox(
        paths,
        account_id=account_id,
        dry_run=dry_run,
        logger=runtime.log,
    )
    runtime.log.debug(
        "import_inbox files=%s successful=%s failed=%s unsupported=%s dry_run=%s",
        summary.total_files,
        summary.successful_files,
        summary.failed_files,
        summary.unsupported_files,
        dry_run,
    )
    if summary.total_files == 0:
        click.echo("No inbox files found.")
        return

    if dry_run:
        click.echo("Dry run: yes")
        click.echo(f"Inbox files: {summary.total_files}")
        click.echo(f"Planned imports: {summary.successful_files}")
        click.echo(f"Planned duplicates: {summary.duplicate_files}")
        click.echo(f"Failed: {summary.failed_files}")
        click.echo(f"Unsupported: {summary.unsupported_files}")
        print_inbox_results(summary.results, dry_run=True)
        return

    click.echo(f"Inbox files: {summary.total_files}")
    click.echo(f"Successful: {summary.successful_files}")
    click.echo(f"Duplicates: {summary.duplicate_files}")
    click.echo(f"Failed: {summary.failed_files}")
    click.echo(f"Unsupported: {summary.unsupported_files}")
    print_inbox_results(summary.results, dry_run=False)


def run_statement_import(
    ctx: click.Context,
    file_path: Path,
    account_id: int,
    *,
    dry_run: bool = False,
) -> None:
    """Import an explicit statement file."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    runtime.log.debug(
        "import_requested file_name=%s suffix=%s account_id=%s dry_run=%s",
        file_path.name,
        file_path.suffix.lower() or "(none)",
        account_id,
        dry_run,
    )
    try:
        if file_path.suffix.lower() == ".csv":
            if dry_run:
                plan = plan_boa_csv_import(
                    paths,
                    file_path,
                    account_id=account_id,
                    logger=runtime.log,
                )
            else:
                summary = import_boa_csv(
                    paths,
                    file_path,
                    account_id=account_id,
                    logger=runtime.log,
                )
        elif file_path.suffix.lower() == ".pdf":
            if dry_run:
                plan = plan_boa_pdf_import(
                    paths,
                    file_path,
                    account_id=account_id,
                    logger=runtime.log,
                )
            else:
                summary = import_boa_pdf(
                    paths,
                    file_path,
                    account_id=account_id,
                    logger=runtime.log,
                )
        else:
            raise ImportFailure(
                f"Unsupported import file type: {file_path.suffix or '(none)'}"
            )
    except ImportFailure as exc:
        runtime.log.debug("import_failed reason=%s", exc)
        raise click.ClickException(str(exc)) from exc

    if dry_run:
        runtime.log.debug(
            "import_dry_run_finished file_name=%s rows_parsed=%s "
            "rows_would_import=%s rows_already_present=%s",
            plan.file_name,
            plan.rows_parsed,
            plan.rows_would_import,
            plan.rows_already_present,
        )
        print_import_plan(plan)
        return

    runtime.log.debug(
        "import_finished file_name=%s rows_parsed=%s rows_imported=%s "
        "rows_skipped_duplicate=%s",
        summary.file_name,
        summary.rows_parsed,
        summary.rows_imported,
        summary.rows_skipped_duplicate,
    )
    print_import_summary(summary)


def print_inbox_results(results, *, dry_run: bool) -> None:
    """Print per-file inbox results."""

    for result in results:
        if result.status == "success":
            if dry_run:
                click.echo(
                    f"would-import  {result.file_name}  parsed={result.rows_parsed} "
                    f"would-import={result.rows_imported} "
                    f"duplicates={result.rows_skipped_duplicate}  "
                    f"canonical={result.processed_path}"
                )
            else:
                click.echo(
                    f"success  {result.file_name}  parsed={result.rows_parsed} "
                    f"imported={result.rows_imported} "
                    f"duplicates={result.rows_skipped_duplicate}"
                )
        elif result.status == "duplicate":
            if dry_run:
                click.echo(
                    f"would-skip-duplicate  {result.file_name}  "
                    f"preserved={result.duplicate_path}  "
                    f"canonical={result.processed_path}"
                )
            else:
                click.echo(
                    f"duplicate  {result.file_name}  preserved={result.duplicate_path}  "
                    f"canonical={result.processed_path}"
                )
        else:
            click.echo(f"{result.status}  {result.file_name}  {result.message}")


def print_import_summary(summary: ImportSummary) -> None:
    """Print the standard import summary."""

    click.echo(f"File: {summary.file_name}")
    click.echo(f"Bank: {summary.bank_name} | Account ID: {summary.account_id}")
    click.echo(f"Rows parsed: {summary.rows_parsed}")
    click.echo(f"Rows imported: {summary.rows_imported}")
    click.echo(f"Duplicate rows skipped: {summary.rows_skipped_duplicate}")


def print_import_plan(plan: ImportPlan) -> None:
    """Print the standard dry-run import plan."""

    click.echo("Dry run: yes")
    click.echo(f"File: {plan.file_name}")
    click.echo(f"Bank: {plan.bank_name} | Account ID: {plan.account_id}")
    click.echo(f"Rows parsed: {plan.rows_parsed}")
    click.echo(f"Rows that would be imported: {plan.rows_would_import}")
    click.echo(f"Rows already present: {plan.rows_already_present}")
    click.echo(f"Processed path: {plan.processed_path}")
    click.echo("Database changed: no")
    click.echo("Files changed: none")


def import_dry_run_from_context(ctx: click.Context) -> bool:
    """Return the parent import group's dry-run flag."""

    current: click.Context | None = ctx
    dry_run = False
    while current is not None:
        if "dry_run" in current.params:
            dry_run = dry_run or bool(current.params["dry_run"])
        current = current.parent
    return dry_run


def runtime_from_context(ctx: click.Context) -> CliRuntime:
    """Return the root BankBuddy runtime context."""

    runtime = ctx.find_root().obj
    if not isinstance(runtime, CliRuntime):
        raise click.ClickException("BankBuddy runtime context is not active.")
    return runtime
