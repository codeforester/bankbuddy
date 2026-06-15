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
from bankbuddy.account_refs import AccountStatementRef
from bankbuddy.account_refs import AccountStatementRefError
from bankbuddy.account_refs import add_account_statement_ref
from bankbuddy.account_refs import display_ref_value
from bankbuddy.account_refs import display_source_format
from bankbuddy.account_refs import list_account_statement_refs
from bankbuddy.account_refs import remove_account_statement_ref
from bankbuddy.accounts import Account
from bankbuddy.accounts import AccountAlreadyExistsError
from bankbuddy.accounts import AccountNotFoundError
from bankbuddy.accounts import AccountSummary
from bankbuddy.accounts import AccountUpdateError
from bankbuddy.accounts import Bank
from bankbuddy.accounts import BankAlreadyExistsError
from bankbuddy.accounts import BankNotFoundError
from bankbuddy.accounts import CountryCodeError
from bankbuddy.accounts import add_account
from bankbuddy.accounts import get_account_summary
from bankbuddy.accounts import list_account_summaries
from bankbuddy.accounts import list_accounts
from bankbuddy.accounts import list_banks
from bankbuddy.accounts import masked_account_number
from bankbuddy.accounts import rename_bank
from bankbuddy.accounts import update_account
from bankbuddy.audit import AccountStatementAudit
from bankbuddy.audit import audit_statement_coverage
from bankbuddy.audit import AuditFilterError
from bankbuddy.categories import Category
from bankbuddy.categories import list_categories
from bankbuddy.database import initialize_database
from bankbuddy.duplicate_diagnostics import DuplicateDiagnosticError
from bankbuddy.duplicate_diagnostics import DuplicateDiagnosticRow
from bankbuddy.duplicate_diagnostics import list_duplicate_transaction_diagnostics
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
from bankbuddy.imports import import_supported_pdf
from bankbuddy.imports import import_xls_statement
from bankbuddy.imports import plan_boa_csv_import
from bankbuddy.imports import plan_supported_pdf_import
from bankbuddy.imports import plan_xls_statement_import
from bankbuddy.paths import resolve_app_paths
from bankbuddy.repairs import BofaPdfRepairFileResult
from bankbuddy.repairs import BofaPdfRepairSummary
from bankbuddy.repairs import RepairSourceFormatError
from bankbuddy.repairs import StatementRepairFileResult
from bankbuddy.repairs import StatementRepairSummary
from bankbuddy.repairs import repair_boa_pdf_imports
from bankbuddy.repairs import repair_statement_imports
from bankbuddy.reports import spending_report
from bankbuddy.runtime import CliRuntime
from bankbuddy.runtime import RuntimeConfigError
from bankbuddy.runtime import create_runtime
from bankbuddy.statements import list_statement_files
from bankbuddy.statements import StatementFilterError
from bankbuddy.statements import StatementListRow
from bankbuddy.statements import statement_summary
from bankbuddy.statements import StatementSummaryRow
from bankbuddy.storage_layout import migrate_storage_layout
from bankbuddy.storage_layout import StorageLayoutError
from bankbuddy.storage_layout import StorageLayoutMigrationSummary
from bankbuddy.transactions import categorize_transaction
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
    click.echo(f"Storage layout: {paths.layout}")
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
def bank() -> None:
    """Manage configured banks."""


@bank.command("list")
@click.pass_context
def bank_list(ctx: click.Context) -> None:
    """List configured banks."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    banks = list_banks(paths)
    runtime.log.debug("bank_list count=%s", len(banks))
    if not banks:
        click.echo("No banks configured.")
        return

    render_bank_list(banks)


@bank.command("rename")
@click.argument("bank_id", type=int)
@click.option("--name", "bank_name", required=True, help="New bank name.")
@click.pass_context
def bank_rename(
    ctx: click.Context,
    bank_id: int,
    bank_name: str,
) -> None:
    """Rename a configured bank."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        renamed = rename_bank(paths, bank_id=bank_id, bank_name=bank_name)
    except (BankAlreadyExistsError, BankNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug("bank_renamed bank_id=%s bank=%s", bank_id, renamed.bank_name)
    click.echo(f"Renamed bank {renamed.bank_id} to {renamed.bank_name}.")


@main.group()
def account() -> None:
    """Manage configured bank accounts."""


@account.command("add")
@click.option("--bank", "bank_name", required=True, help="Bank name.")
@click.option(
    "--country",
    required=True,
    help="ISO 3166-1 alpha-2 country code or supported alias, such as US or IN.",
)
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
    hidden=True,
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
    except (AccountAlreadyExistsError, CountryCodeError) as exc:
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

    render_account_list(accounts)


@account.command("update")
@click.argument("account_id", type=int)
@click.option("--display-name", help="Set or clear the friendly account label.")
@click.pass_context
def account_update(
    ctx: click.Context,
    account_id: int,
    display_name: str | None,
) -> None:
    """Update safe account metadata."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        updated = update_account(
            paths,
            account_id=account_id,
            display_name=display_name,
        )
    except (AccountNotFoundError, AccountUpdateError) as exc:
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug("account_updated account_id=%s", updated.account_id)
    click.echo(f"Updated account {updated.account_id}.")


@account.command("summary")
@click.pass_context
def account_summary(ctx: click.Context) -> None:
    """Summarize configured bank accounts."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    accounts = list_account_summaries(paths)
    runtime.log.debug("account_summary count=%s", len(accounts))
    if not accounts:
        click.echo("No accounts configured.")
        return

    render_account_summary(accounts)


@account.command("show")
@click.argument("account_id", type=int)
@click.option(
    "--show-full-account-number",
    is_flag=True,
    help="Show the full account number for this account.",
)
@click.pass_context
def account_show(
    ctx: click.Context,
    account_id: int,
    show_full_account_number: bool,
) -> None:
    """Show one configured bank account."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    account = get_account_summary(paths, account_id=account_id)
    if account is None:
        raise click.ClickException(f"Account not found: {account_id}")

    runtime.log.debug("account_show account_id=%s", account_id)
    render_account_detail(
        account,
        show_full_account_number=show_full_account_number,
    )


@account.group("ref")
def account_ref() -> None:
    """Manage parser-visible account references."""


@account_ref.command("add")
@click.option("--account-id", required=True, type=int, help="Configured account id.")
@click.option(
    "--type",
    "ref_type",
    required=True,
    type=click.Choice(
        [
            "full_account_number",
            "full-account-number",
            "last4",
            "masked_account",
            "masked-account",
            "product",
        ],
        case_sensitive=False,
    ),
    help="Statement reference type.",
)
@click.option("--value", "ref_value", required=True, help="Reference value.")
@click.option(
    "--source-format",
    help="Optional parser source format, such as boa_pdf. Defaults to any.",
)
@click.pass_context
def account_ref_add(
    ctx: click.Context,
    account_id: int,
    ref_type: str,
    ref_value: str,
    source_format: str | None,
) -> None:
    """Add an account statement reference.

    \b
    Examples:
      Apple Card product identity:
        bankbuddy account ref add --account-id 5 --type product --value "Apple Card" --source-format apple_card_pdf
      Last-four statement suffix:
        bankbuddy account ref add --account-id 1 --type last4 --value 1145 --source-format boa_pdf
      Full account number:
        bankbuddy account ref add --account-id 1 --type full_account_number --value <actual-number>
    """

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        statement_ref = add_account_statement_ref(
            paths,
            account_id=account_id,
            ref_type=ref_type,
            ref_value=ref_value,
            source_format=source_format,
        )
    except AccountStatementRefError as exc:
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug(
        "account_ref_added statement_ref_id=%s account_id=%s type=%s source=%s",
        statement_ref.statement_ref_id,
        statement_ref.account_id,
        statement_ref.ref_type,
        display_source_format(statement_ref.source_format),
    )
    click.echo(
        f"Added account statement ref {statement_ref.statement_ref_id} "
        f"for account {statement_ref.account_id}."
    )


@account_ref.command("list")
@click.option("--account-id", type=int, help="Filter by configured account id.")
@click.pass_context
def account_ref_list(ctx: click.Context, account_id: int | None) -> None:
    """List account statement references."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    refs = list_account_statement_refs(paths, account_id=account_id)
    runtime.log.debug("account_ref_list count=%s account_id=%s", len(refs), account_id)
    if not refs:
        click.echo("No account statement refs configured.")
        return

    render_account_statement_refs(refs)


@account_ref.command("remove")
@click.argument("statement_ref_id", type=int)
@click.pass_context
def account_ref_remove(ctx: click.Context, statement_ref_id: int) -> None:
    """Remove an account statement reference."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        remove_account_statement_ref(paths, statement_ref_id=statement_ref_id)
    except AccountStatementRefError as exc:
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug("account_ref_removed statement_ref_id=%s", statement_ref_id)
    click.echo(f"Removed account statement ref {statement_ref_id}.")


def render_account_summary(accounts: list[AccountSummary]) -> None:
    """Render account summaries as an aligned table."""

    render_pretty_table(
        [
            "ID",
            "Bank",
            "Name",
            "Type",
            "Currency",
            "Account",
            "Latest Balance",
            "As Of",
            "Source",
        ],
        [
            [
                str(account.account_id),
                account.bank_name,
                account.display_name or "-",
                account.account_type,
                account.currency,
                masked_account_number(account.account_number),
                format_account_balance(account),
                account.latest_balance_as_of_date or "-",
                account.latest_balance_source or "-",
            ]
            for account in accounts
        ],
        [
            "right",
            "left",
            "left",
            "left",
            "left",
            "left",
            "right",
            "left",
            "left",
        ],
    )


def render_account_list(accounts: list[Account]) -> None:
    """Render configured accounts as an aligned table."""

    render_pretty_table(
        ["ID", "Bank", "Name", "Type", "Currency", "Account"],
        [
            [
                str(account.account_id),
                account.bank_name,
                account.display_name or "-",
                account.account_type,
                account.currency,
                masked_account_number(account.account_number),
            ]
            for account in accounts
        ],
        ["right", "left", "left", "left", "left", "left"],
    )


def render_account_detail(
    account: AccountSummary,
    *,
    show_full_account_number: bool = False,
) -> None:
    """Render a single account detail view."""

    click.echo(f"ID: {account.account_id}")
    click.echo(f"Bank: {account.bank_name}")
    click.echo(f"Country: {account.country}")
    click.echo(f"Name: {account.display_name or '-'}")
    click.echo(f"Type: {account.account_type}")
    click.echo(f"Currency: {account.currency}")
    account_number = (
        account.account_number
        if show_full_account_number
        else masked_account_number(account.account_number)
    )
    click.echo(f"Account: {account_number}")
    click.echo(f"Latest balance: {format_account_balance(account)}")
    click.echo(f"Latest balance as of: {account.latest_balance_as_of_date or '-'}")
    click.echo(f"Latest balance source: {account.latest_balance_source or '-'}")


def render_account_statement_refs(refs: list[AccountStatementRef]) -> None:
    """Render account statement refs as an aligned table."""

    render_pretty_table(
        ["ID", "Account", "Bank", "Type", "Value", "Source"],
        [
            [
                str(ref.statement_ref_id),
                str(ref.account_id),
                ref.bank_name,
                ref.ref_type,
                display_ref_value(ref),
                display_source_format(ref.source_format),
            ]
            for ref in refs
        ],
        ["right", "right", "left", "left", "left", "left"],
    )


def render_bank_list(banks: list[Bank]) -> None:
    """Render configured banks as an aligned table."""

    render_pretty_table(
        ["ID", "Bank", "Country", "Currency"],
        [
            [
                str(bank.bank_id),
                bank.bank_name,
                bank.country,
                bank.default_currency,
            ]
            for bank in banks
        ],
        ["right", "left", "left", "left"],
    )


def format_account_balance(account: AccountSummary) -> str:
    """Return a display-safe latest balance value."""

    if (
        account.latest_balance_minor_units is None
        or account.latest_balance_currency is None
    ):
        return "-"
    return (
        f"{account.latest_balance_currency} "
        f"{format_minor_units(account.latest_balance_minor_units)}"
    )


@main.group()
def category() -> None:
    """Inspect transaction categories."""


@category.command("list")
@click.pass_context
def category_list(ctx: click.Context) -> None:
    """List available transaction categories."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    rows = list_categories(paths)
    runtime.log.debug("category_list count=%s", len(rows))
    render_categories(rows)


def render_categories(rows: list[Category]) -> None:
    """Render available categories."""

    render_pretty_table(
        ["Name", "Kind", "System"],
        [
            [
                row.category_name,
                row.category_kind,
                "yes" if row.is_system else "no",
            ]
            for row in rows
        ],
        ["left", "left", "left"],
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
@click.option("--category", "category_name", help="Filter by transaction category.")
@click.option(
    "--uncategorized",
    is_flag=True,
    help="Show only uncategorized transactions.",
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
    category_name: str | None,
    uncategorized: bool,
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
            category_name=category_name,
            uncategorized=uncategorized,
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
        "direction=%s category=%s uncategorized=%s sort=%s order=%s "
        "view=%s format=%s summary=%s",
        len(rows),
        account_id,
        bank_name,
        currency,
        account_number_suffix(account_number),
        account_number_suffix(account_last4),
        normalized_date_from,
        normalized_date_to,
        direction,
        category_name,
        uncategorized,
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


@tx.command("categorize")
@click.argument("transaction_id", type=int)
@click.argument("category_name")
@click.pass_context
def tx_categorize(
    ctx: click.Context,
    transaction_id: int,
    category_name: str,
) -> None:
    """Assign one transaction to an existing category."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        update = categorize_transaction(
            paths,
            transaction_id=transaction_id,
            category_name=category_name,
        )
    except TransactionFilterError as exc:
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug(
        "tx_categorize transaction_id=%s category=%s",
        update.transaction_id,
        update.category_name,
    )
    click.echo(
        f"Updated transaction {update.transaction_id} category to "
        f"{update.category_name}."
    )


@tx.command("duplicates")
@click.option("--bank", "bank_name", help="Filter by exact bank name.")
@click.option("--account-id", type=int, help="Filter by configured account id.")
@click.option("--account-last4", help="Filter by unambiguous account suffix.")
@click.option(
    "--year",
    type=click.IntRange(min=1900, max=9999),
    help="Filter by statement end year.",
)
@click.option("--attempt-id", type=int, help="Filter by import attempt id.")
@click.option("--file-id", type=int, help="Filter by import file id.")
@click.pass_context
def tx_duplicates(
    ctx: click.Context,
    bank_name: str | None,
    account_id: int | None,
    account_last4: str | None,
    year: int | None,
    attempt_id: int | None,
    file_id: int | None,
) -> None:
    """Inspect rows skipped as duplicate transactions."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        rows = list_duplicate_transaction_diagnostics(
            paths,
            bank_name=bank_name,
            account_id=account_id,
            account_last4=account_last4,
            year=year,
            attempt_id=attempt_id,
            file_id=file_id,
        )
    except DuplicateDiagnosticError as exc:
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug(
        "tx_duplicates count=%s bank=%s account_id=%s account_last4=%s "
        "year=%s attempt_id=%s file_id=%s",
        len(rows),
        bank_name,
        account_id,
        account_number_suffix(account_last4),
        year,
        attempt_id,
        file_id,
    )
    if not rows:
        click.echo("No duplicate transactions found.")
        return

    render_duplicate_transaction_rows(rows)


def render_duplicate_transaction_rows(rows: list[DuplicateDiagnosticRow]) -> None:
    """Render reconstructed duplicate transaction diagnostics."""

    render_pretty_table(
        [
            "Attempt",
            "Bank",
            "Account",
            "Statement",
            "File",
            "Row",
            "Date",
            "Amount",
            "Candidate",
            "Original ID",
            "Original Row",
            "Original Date",
            "Original Amount",
            "Original",
        ],
        [
            [
                str(row.attempt_id),
                row.bank_name,
                row.account_display,
                row.statement_period,
                row.file_name,
                row.candidate_source_row_key,
                row.candidate_date,
                format_minor_units(row.candidate_amount_minor_units),
                row.candidate_description,
                str(row.matched_transaction_id),
                row.matched_source_row_key or "-",
                row.matched_date,
                format_minor_units(row.matched_amount_minor_units),
                row.matched_description,
            ]
            for row in rows
        ],
        [
            "right",
            "left",
            "left",
            "left",
            "left",
            "right",
            "left",
            "right",
            "left",
            "right",
            "right",
            "left",
            "right",
            "left",
        ],
    )


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
        "category": TransactionColumn(
            "Category",
            "category",
            "left",
            lambda row: row.category_name,
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
            columns["category"],
            columns["description"],
        ]
    return [
        columns["id"],
        columns["date"],
        columns["account"],
        columns["amount"],
        columns["currency"],
        columns["category"],
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


def render_pretty_table(
    headers: list[str],
    rows: list[list[str]],
    aligns: list[ColumnAlign],
) -> None:
    """Render an aligned pretty table from precomputed string rows."""

    widths = [
        max([len(header)] + [len(row[index]) for row in rows])
        for index, header in enumerate(headers)
    ]
    click.echo(format_pretty_row(headers, widths, aligns))
    click.echo("-+-".join("-" * width for width in widths))
    for row in rows:
        click.echo(format_pretty_row(row, widths, aligns))


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

    headers = ["Currency", "Transactions", "Debits", "Credits", "Net"]
    aligns: list[ColumnAlign] = ["left", "right", "right", "right", "right"]
    values = [
        [
            row.currency,
            str(row.transaction_count),
            format_minor_units(row.debit_minor_units),
            format_minor_units(row.credit_minor_units),
            format_minor_units(row.net_minor_units),
        ]
        for row in summarize_transactions(rows)
    ]
    widths = [
        max([len(header)] + [len(row[index]) for row in values])
        for index, header in enumerate(headers)
    ]

    click.echo("Summary")
    click.echo(format_pretty_row(headers, widths, aligns))
    click.echo("-+-".join("-" * width for width in widths))
    for row_values in values:
        click.echo(format_pretty_row(row_values, widths, aligns))


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
def audit() -> None:
    """Audit imported data quality."""


@audit.command("statements")
@click.option("--bank", "bank_name", help="Filter by exact bank name.")
@click.option("--account-id", type=int, help="Filter by configured account id.")
@click.option("--account-last4", help="Filter by unambiguous account suffix.")
@click.option("--years", help="Comma-separated calendar years to audit.")
@click.option("--from", "date_from", help="Inclusive start date, YYYY-MM-DD.")
@click.option("--to", "date_to", help="Inclusive end date, YYYY-MM-DD.")
@click.pass_context
def audit_statements(
    ctx: click.Context,
    bank_name: str | None,
    account_id: int | None,
    account_last4: str | None,
    years: str | None,
    date_from: str | None,
    date_to: str | None,
) -> None:
    """Audit imported statement coverage."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    normalized_date_from = validate_iso_date(date_from, "--from")
    normalized_date_to = validate_iso_date(date_to, "--to")
    try:
        parsed_years = parse_audit_years(years)
        audits = audit_statement_coverage(
            paths,
            bank_name=bank_name,
            account_id=account_id,
            account_last4=account_last4,
            years=parsed_years,
            date_from=normalized_date_from,
            date_to=normalized_date_to,
        )
    except AuditFilterError as exc:
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug(
        "audit_statements count=%s bank=%s account_id=%s account_last4=%s "
        "years=%s date_from=%s date_to=%s",
        len(audits),
        bank_name,
        account_id,
        account_number_suffix(account_last4),
        parsed_years,
        normalized_date_from,
        normalized_date_to,
    )
    if not audits:
        click.echo("No imported statements found.")
        return

    render_statement_audits(audits)


def parse_audit_years(years: str | None) -> list[int] | None:
    """Parse a comma-separated year selector."""

    if years is None or not years.strip():
        return None

    parsed_years: list[int] = []
    for raw_year in years.split(","):
        year = raw_year.strip()
        if len(year) != 4 or not year.isdigit():
            raise AuditFilterError("Years must be four-digit values.")
        parsed_years.append(int(year))
    return parsed_years


def render_statement_audits(audits: list[AccountStatementAudit]) -> None:
    """Render statement coverage audit results."""

    for index, audit_result in enumerate(audits):
        if index:
            click.echo("")
        render_pretty_table(
            ["Account", "Bank", "Window"],
            [[
                audit_result.account_display,
                audit_result.bank_name,
                (
                    f"{audit_result.window_start.isoformat()} to "
                    f"{audit_result.window_end.isoformat()}"
                ),
            ]],
            ["left", "left", "left"],
        )
        click.echo("")
        render_pretty_table(
            ["Status", "Period", "File"],
            [
                [
                    finding.status,
                    (
                        f"{finding.period_start.isoformat()} to "
                        f"{finding.period_end.isoformat()}"
                    ),
                    finding.file_name or "-",
                ]
                for finding in audit_result.findings
            ],
            ["left", "left", "left"],
        )


@main.group()
def statements() -> None:
    """Inspect imported statement files."""


@statements.command("summary")
@click.option(
    "--by",
    "group_by",
    type=click.Choice(["year", "month"], case_sensitive=False),
    default="year",
    show_default=True,
    help="Group statement files by statement end year or month.",
)
@click.option("--bank", "bank_name", help="Filter by exact bank name.")
@click.option("--account-id", type=int, help="Filter by configured account id.")
@click.option("--account-last4", help="Filter by unambiguous account suffix.")
@click.option("--years", help="Comma-separated statement end years.")
@click.pass_context
def statements_summary(
    ctx: click.Context,
    group_by: str,
    bank_name: str | None,
    account_id: int | None,
    account_last4: str | None,
    years: str | None,
) -> None:
    """Summarize imported statement files."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        parsed_years = parse_audit_years(years)
        rows = statement_summary(
            paths,
            group_by=group_by.lower(),
            bank_name=bank_name,
            account_id=account_id,
            account_last4=account_last4,
            years=parsed_years,
        )
    except (AuditFilterError, StatementFilterError) as exc:
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug(
        "statements_summary count=%s group_by=%s bank=%s account_id=%s "
        "account_last4=%s years=%s",
        len(rows),
        group_by,
        bank_name,
        account_id,
        account_number_suffix(account_last4),
        parsed_years,
    )
    if not rows:
        click.echo("No imported statements found.")
        return

    render_statement_summary(rows)


@statements.command("list")
@click.option("--bank", "bank_name", help="Filter by exact bank name.")
@click.option("--account-id", type=int, help="Filter by configured account id.")
@click.option("--account-last4", help="Filter by unambiguous account suffix.")
@click.option(
    "--year",
    type=click.IntRange(min=1900, max=9999),
    help="Filter by statement end year.",
)
@click.pass_context
def statements_list(
    ctx: click.Context,
    bank_name: str | None,
    account_id: int | None,
    account_last4: str | None,
    year: int | None,
) -> None:
    """List imported statement files."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        rows = list_statement_files(
            paths,
            bank_name=bank_name,
            account_id=account_id,
            account_last4=account_last4,
            year=year,
        )
    except StatementFilterError as exc:
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug(
        "statements_list count=%s bank=%s account_id=%s account_last4=%s year=%s",
        len(rows),
        bank_name,
        account_id,
        account_number_suffix(account_last4),
        year,
    )
    if not rows:
        click.echo("No imported statements found.")
        return

    render_statement_list(rows)


def render_statement_summary(rows: list[StatementSummaryRow]) -> None:
    """Render grouped statement inventory rows."""

    render_pretty_table(
        [
            "Bank",
            "Account",
            "Year",
            "Month",
            "Files",
            "Period Start",
            "Period End",
            "Transactions",
            "Duplicate Tx",
        ],
        [
            [
                row.bank_name,
                row.account_display,
                str(row.year),
                f"{row.month:02d}" if row.month is not None else "-",
                str(row.file_count),
                row.period_start,
                row.period_end,
                str(row.rows_imported),
                str(row.rows_skipped_duplicate),
            ]
            for row in rows
        ],
        [
            "left",
            "left",
            "right",
            "right",
            "right",
            "left",
            "left",
            "right",
            "right",
        ],
    )


def render_statement_list(rows: list[StatementListRow]) -> None:
    """Render imported statement file rows."""

    render_pretty_table(
        [
            "Bank",
            "Account",
            "Period",
            "File",
            "Imported",
            "Transactions",
            "Duplicate Tx",
        ],
        [
            [
                row.bank_name,
                row.account_display,
                row.period,
                row.file_name,
                row.imported_at or "-",
                str(row.rows_imported),
                str(row.rows_skipped_duplicate),
            ]
            for row in rows
        ],
        ["left", "left", "left", "left", "left", "right", "right"],
    )


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


@main.group()
def storage() -> None:
    """Manage local BankBuddy storage."""


@storage.command("migrate-layout")
@click.option(
    "--dry-run/--apply",
    default=True,
    help="Preview the migration or apply it. Defaults to dry-run.",
)
@click.pass_context
def storage_migrate_layout_command(ctx: click.Context, dry_run: bool) -> None:
    """Migrate a legacy app home into the canonical storage layout."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        summary = migrate_storage_layout(paths, dry_run=dry_run)
    except StorageLayoutError as exc:
        runtime.log.debug("storage_migrate_layout_failed reason=%s", exc)
        raise click.ClickException(str(exc)) from exc

    runtime.log.debug(
        "storage_migrate_layout dry_run=%s layout=%s already_canonical=%s "
        "processed_paths_to_update=%s duplicate_paths_to_update=%s",
        summary.dry_run,
        paths.layout,
        summary.already_canonical,
        summary.processed_paths_to_update,
        summary.duplicate_paths_to_update,
    )
    render_storage_layout_migration(summary, current_layout=paths.layout)


def render_storage_layout_migration(
    summary: StorageLayoutMigrationSummary,
    *,
    current_layout: str,
) -> None:
    """Print a storage layout migration summary."""

    click.echo(f"Dry run: {'yes' if summary.dry_run else 'no'}")
    click.echo(f"Current layout: {current_layout}")
    click.echo("Target layout: canonical")
    if summary.already_canonical:
        click.echo("Already canonical: yes")
        return

    if summary.database_move is not None:
        click.echo(
            f"Database: {summary.database_move.source} -> "
            f"{summary.database_move.target}"
        )
    else:
        click.echo("Database: -")
    for move in summary.directory_moves:
        click.echo(f"Directory: {move.source} -> {move.target}")
    click.echo(f"Processed paths to update: {summary.processed_paths_to_update}")
    click.echo(f"Duplicate paths to update: {summary.duplicate_paths_to_update}")
    click.echo(f"Changes applied: {'yes' if summary.changes_applied else 'no'}")


@main.group()
def repair() -> None:
    """Repair historical imported data."""


@repair.command("bofa-pdf-imports")
@click.option(
    "--apply",
    "apply_changes",
    is_flag=True,
    help="Apply database changes. Defaults to dry-run.",
)
@click.pass_context
def repair_bofa_pdf_imports_command(
    ctx: click.Context,
    apply_changes: bool,
) -> None:
    """Repair historical Bank of America PDF import rows."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    summary = repair_boa_pdf_imports(paths, dry_run=not apply_changes)
    runtime.log.debug(
        "repair_bofa_pdf_imports dry_run=%s files_scanned=%s files_changed=%s "
        "files_failed=%s hashes_updated=%s rows_inserted=%s attempts_updated=%s",
        summary.dry_run,
        summary.files_scanned,
        summary.files_changed,
        summary.files_failed,
        summary.hashes_updated,
        summary.rows_inserted,
        summary.attempts_updated,
    )
    render_bofa_pdf_repair_summary(summary)


@repair.command("statement-imports")
@click.option(
    "--source-format",
    required=True,
    help="Imported statement source format to repair, such as boa_pdf.",
)
@click.option(
    "--apply",
    "apply_changes",
    is_flag=True,
    help="Apply database changes. Defaults to dry-run.",
)
@click.pass_context
def repair_statement_imports_command(
    ctx: click.Context,
    source_format: str,
    apply_changes: bool,
) -> None:
    """Repair historical statement import rows by source format."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        summary = repair_statement_imports(
            paths,
            source_format=source_format,
            dry_run=not apply_changes,
        )
    except RepairSourceFormatError as exc:
        raise click.ClickException(str(exc)) from exc
    runtime.log.debug(
        "repair_statement_imports source_format=%s dry_run=%s files_scanned=%s "
        "files_changed=%s files_failed=%s hashes_updated=%s rows_inserted=%s "
        "attempts_updated=%s",
        summary.source_format,
        summary.dry_run,
        summary.files_scanned,
        summary.files_changed,
        summary.files_failed,
        summary.hashes_updated,
        summary.rows_inserted,
        summary.attempts_updated,
    )
    render_statement_repair_summary(summary)


def render_bofa_pdf_repair_summary(summary: BofaPdfRepairSummary) -> None:
    """Render a Bank of America PDF repair summary."""

    render_statement_repair_summary(summary)


def render_statement_repair_summary(summary: StatementRepairSummary) -> None:
    """Render a statement import repair summary."""

    click.echo(f"Source format: {summary.source_format}")
    click.echo(f"Dry run: {'yes' if summary.dry_run else 'no'}")
    click.echo(f"Files scanned: {summary.files_scanned}")
    click.echo(f"Files changed: {summary.files_changed}")
    click.echo(f"Files failed: {summary.files_failed}")
    click.echo(f"Transaction hashes to update: {summary.hashes_updated}")
    click.echo(f"Rows to insert: {summary.rows_inserted}")
    click.echo(f"Import attempts to update: {summary.attempts_updated}")
    if summary.results:
        render_statement_repair_results(summary.results)
    database_changed = not summary.dry_run and summary.files_changed > 0
    click.echo(f"Database changed: {'yes' if database_changed else 'no'}")


def render_bofa_pdf_repair_results(results: list[BofaPdfRepairFileResult]) -> None:
    """Render per-file repair results."""

    render_statement_repair_results(results)


def render_statement_repair_results(results: list[StatementRepairFileResult]) -> None:
    """Render per-file statement repair results."""

    render_pretty_table(
        [
            "Status",
            "File",
            "Parsed",
            "Hash Updates",
            "Inserts",
            "Attempt Updates",
            "Message",
        ],
        [
            [
                result.status,
                result.file_name,
                str(result.rows_parsed),
                str(result.hashes_updated),
                str(result.rows_inserted),
                str(result.attempts_updated),
                result.message or "-",
            ]
            for result in results
        ],
        ["left", "left", "right", "right", "right", "right", "left"],
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
                plan = plan_supported_pdf_import(
                    paths,
                    file_path,
                    account_id=account_id,
                    logger=runtime.log,
                )
            else:
                summary = import_supported_pdf(
                    paths,
                    file_path,
                    account_id=account_id,
                    logger=runtime.log,
                )
        elif file_path.suffix.lower() == ".xls":
            if dry_run:
                plan = plan_xls_statement_import(
                    paths,
                    file_path,
                    account_id=account_id,
                    logger=runtime.log,
                )
            else:
                summary = import_xls_statement(
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
    if (
        summary.latest_balance_minor_units is not None
        and summary.latest_balance_currency is not None
        and summary.latest_balance_as_of_date is not None
    ):
        click.echo(
            "Latest balance: "
            f"{summary.latest_balance_currency} "
            f"{format_minor_units(summary.latest_balance_minor_units)} "
            f"as of {summary.latest_balance_as_of_date}"
        )


def print_import_plan(plan: ImportPlan) -> None:
    """Print the standard dry-run import plan."""

    click.echo("Dry run: yes")
    click.echo(f"File: {plan.file_name}")
    click.echo(f"Bank: {plan.bank_name} | Account ID: {plan.account_id}")
    click.echo(f"Rows parsed: {plan.rows_parsed}")
    click.echo(f"Rows that would be imported: {plan.rows_would_import}")
    click.echo(f"Rows already present: {plan.rows_already_present}")
    click.echo(f"Processed path: {plan.processed_path}")
    if (
        plan.latest_balance_minor_units is not None
        and plan.latest_balance_currency is not None
        and plan.latest_balance_as_of_date is not None
    ):
        click.echo(
            "Latest balance: "
            f"{plan.latest_balance_currency} "
            f"{format_minor_units(plan.latest_balance_minor_units)} "
            f"as of {plan.latest_balance_as_of_date}"
        )
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
