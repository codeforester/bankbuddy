"""Command line interface for BankBuddy."""

from __future__ import annotations

import click

from bankbuddy import __version__
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
