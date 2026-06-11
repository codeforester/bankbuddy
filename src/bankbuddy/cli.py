"""Command line interface for BankBuddy."""

from __future__ import annotations

import click

from bankbuddy import __version__
from bankbuddy.accounts import AccountAlreadyExistsError
from bankbuddy.accounts import add_account
from bankbuddy.accounts import list_accounts
from bankbuddy.accounts import masked_account_number
from bankbuddy.database import initialize_database
from bankbuddy.paths import resolve_app_paths


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="bank-buddy")
def main() -> None:
    """Local-first personal finance tracking."""


@main.command()
def status() -> None:
    """Show the local BankBuddy app state."""

    paths = resolve_app_paths()
    initialized = "yes" if paths.database.exists() else "no"

    click.echo(f"Home: {paths.root}")
    click.echo(f"Database: {paths.database}")
    click.echo(f"Initialized: {initialized}")


@main.command("init")
def init_command() -> None:
    """Initialize the local BankBuddy app directory and database."""

    paths = resolve_app_paths()
    initialize_database(paths)
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
def account_add(
    bank_name: str,
    country: str,
    account_number: str,
    account_type: str,
    currency: str,
    statement_account_ref: str | None,
    display_name: str | None,
) -> None:
    """Add a bank account."""

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

    click.echo(f"Added account {account.account_id} for {account.bank_name}")


@account.command("list")
def account_list() -> None:
    """List configured bank accounts."""

    paths = resolve_app_paths()
    accounts = list_accounts(paths)
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
