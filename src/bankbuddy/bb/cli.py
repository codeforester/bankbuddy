"""Command line interface for BankBuddy v2 workflows."""

from __future__ import annotations

import sqlite3

import click

from bankbuddy import __version__
from bankbuddy.paths import resolve_app_paths
from bankbuddy.runtime import CliRuntime
from bankbuddy.runtime import RuntimeConfigError
from bankbuddy.runtime import create_runtime


BB_FOUNDATION_TABLES = {
    "BB_CURRENCY",
    "BB_DOCUMENT",
    "BB_DOCUMENT_OBJECT",
    "BB_DOCUMENT_VIEW",
    "BB_ENTITY",
    "BB_ENTITY_ATTRIBUTE",
    "BB_ENTITY_ATTRIBUTE_TYPE",
    "BB_EXTRACTION_RUN",
    "BB_HOUSEHOLD",
    "BB_HOUSEHOLD_MEMBER",
    "BB_IMPORT_ATTEMPT",
    "BB_JURISDICTION",
    "BB_OBSERVATION",
    "BB_OBSERVATION_EVIDENCE",
    "BB_OBSERVATION_TYPE",
    "BB_PARSER",
    "BB_PERSON",
    "BB_RELATIONSHIP",
    "BB_RELATIONSHIP_TYPE",
    "BB_STORAGE_ROOT",
}

LEGACY_TABLES = {
    "accounts",
    "banks",
    "import_attempts",
    "import_files",
    "tax_documents",
    "transactions",
}


@click.group(
    name="bb",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="bb")
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
    """BankBuddy v2 financial intelligence workflows."""

    try:
        runtime = create_runtime(
            debug=debug,
            environment=environment,
            config_path=config_path,
            keep_temp=keep_temp,
            log_file=log_file,
            cli_name="bb",
        )
    except (OSError, RuntimeConfigError) as exc:
        raise click.ClickException(str(exc)) from exc

    ctx.obj = runtime
    ctx.call_on_close(runtime.cleanup)


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show the local BankBuddy v2 app state."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    table_names = _database_table_names(paths.database)
    initialized = "yes" if paths.database.exists() else "no"
    bb_table_count = len([name for name in table_names if name.startswith("BB_")])
    has_v2_foundation = BB_FOUNDATION_TABLES.issubset(table_names)
    has_legacy_tables = bool(LEGACY_TABLES.intersection(table_names))

    runtime.log.debug(
        "bb_status environment=%s data_home=%s database=%s initialized=%s "
        "bb_table_count=%s v2_foundation=%s legacy_tables=%s",
        paths.environment,
        paths.root,
        paths.database,
        initialized,
        bb_table_count,
        has_v2_foundation,
        has_legacy_tables,
    )

    click.echo("CLI: bb")
    click.echo(f"Environment: {paths.environment}")
    click.echo(f"Storage layout: {paths.layout}")
    click.echo(f"Data home: {paths.root}")
    click.echo(f"Database: {paths.database}")
    click.echo(f"Initialized: {initialized}")
    click.echo(f"V2 foundation: {_yes_no(has_v2_foundation)}")
    click.echo(f"BB tables: {bb_table_count}")
    click.echo(f"Legacy tables: {'present' if has_legacy_tables else 'absent'}")


def _database_table_names(database_path) -> set[str]:
    if not database_path.exists():
        return set()
    with sqlite3.connect(database_path) as conn:
        return {
            str(row[0])
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def runtime_from_context(ctx: click.Context) -> CliRuntime:
    """Return the root bb runtime context."""

    runtime = ctx.find_root().obj
    if not isinstance(runtime, CliRuntime):
        raise click.ClickException("bb runtime context is not active.")
    return runtime
