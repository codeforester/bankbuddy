"""Command line interface for BankBuddy."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click

from bankbuddy import __version__
from bankbuddy.accounts import AccountAlreadyExistsError
from bankbuddy.accounts import add_account
from bankbuddy.accounts import list_accounts
from bankbuddy.accounts import masked_account_number
from bankbuddy.database import initialize_database
from bankbuddy.imports import ImportFailure
from bankbuddy.imports import import_boa_csv
from bankbuddy.imports import import_boa_pdf
from bankbuddy.paths import resolve_app_paths
from bankbuddy.runtime import CliRuntime
from bankbuddy.runtime import RuntimeConfigError
from bankbuddy.runtime import create_runtime
from bankbuddy.transactions import format_minor_units
from bankbuddy.transactions import list_transactions


@click.group(
    name="bank-buddy",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="bank-buddy")
@click.option(
    "-v",
    "--debug",
    is_flag=True,
    help="Enable DEBUG logging on the user-facing stream.",
)
@click.option("--environment", help="Set the Base CLI environment.")
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
    paths = resolve_app_paths()
    initialized = "yes" if paths.database.exists() else "no"
    runtime.log.debug(
        "status home=%s database=%s initialized=%s",
        paths.root,
        paths.database,
        initialized,
    )

    click.echo(f"Home: {paths.root}")
    click.echo(f"Database: {paths.database}")
    click.echo(f"Initialized: {initialized}")


@main.command("init")
@click.pass_context
def init_command(ctx: click.Context) -> None:
    """Initialize the local BankBuddy app directory and database."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths()
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
    paths = resolve_app_paths()
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
    paths = resolve_app_paths()
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
@click.option("--from", "date_from", help="Inclusive start date, YYYY-MM-DD.")
@click.option("--to", "date_to", help="Inclusive end date, YYYY-MM-DD.")
@click.pass_context
def tx_list(
    ctx: click.Context,
    account_id: int | None,
    date_from: str | None,
    date_to: str | None,
) -> None:
    """List imported transactions."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths()
    normalized_date_from = validate_iso_date(date_from, "--from")
    normalized_date_to = validate_iso_date(date_to, "--to")
    rows = list_transactions(
        paths,
        account_id=account_id,
        date_from=normalized_date_from,
        date_to=normalized_date_to,
    )
    runtime.log.debug(
        "tx_list count=%s account_id=%s date_from=%s date_to=%s",
        len(rows),
        account_id,
        normalized_date_from,
        normalized_date_to,
    )
    if not rows:
        click.echo("No transactions found.")
        return

    click.echo("ID  Date  Account  Amount  Currency  Description")
    for row in rows:
        click.echo(
            f"{row.transaction_id}  {row.transaction_date}  "
            f"{row.account_display}  {format_minor_units(row.amount_minor_units)}  "
            f"{row.currency}  {row.description}"
        )


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


@main.command("import")
@click.option(
    "--file",
    "file_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="CSV file to import.",
)
@click.option("--account-id", required=True, type=int, help="Configured account id.")
@click.pass_context
def import_command(ctx: click.Context, file_path: Path, account_id: int) -> None:
    """Import an explicit statement file."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths()
    runtime.log.debug(
        "import_requested file_name=%s suffix=%s account_id=%s",
        file_path.name,
        file_path.suffix.lower() or "(none)",
        account_id,
    )
    try:
        if file_path.suffix.lower() == ".csv":
            summary = import_boa_csv(
                paths,
                file_path,
                account_id=account_id,
                logger=runtime.log,
            )
        elif file_path.suffix.lower() == ".pdf":
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

    runtime.log.debug(
        "import_finished file_name=%s rows_parsed=%s rows_imported=%s "
        "rows_skipped_duplicate=%s",
        summary.file_name,
        summary.rows_parsed,
        summary.rows_imported,
        summary.rows_skipped_duplicate,
    )
    click.echo(f"File: {summary.file_name}")
    click.echo(f"Bank: {summary.bank_name} | Account ID: {summary.account_id}")
    click.echo(f"Rows parsed: {summary.rows_parsed}")
    click.echo(f"Rows imported: {summary.rows_imported}")
    click.echo(f"Duplicate rows skipped: {summary.rows_skipped_duplicate}")


def runtime_from_context(ctx: click.Context) -> CliRuntime:
    """Return the root BankBuddy runtime context."""

    runtime = ctx.find_root().obj
    if not isinstance(runtime, CliRuntime):
        raise click.ClickException("BankBuddy runtime context is not active.")
    return runtime
