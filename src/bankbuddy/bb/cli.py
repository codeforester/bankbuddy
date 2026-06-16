"""Command line interface for BankBuddy v2 workflows."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import click

from bankbuddy import __version__
from bankbuddy.database import initialize_database
from bankbuddy.bb.documents import DocumentImportError
from bankbuddy.bb.documents import DocumentSummary
from bankbuddy.bb.documents import get_document_summary
from bankbuddy.bb.documents import import_document
from bankbuddy.bb.documents import list_documents
from bankbuddy.bb.documents import plan_document_import
from bankbuddy.paths import resolve_app_paths
from bankbuddy.bb.storage import ensure_financial_storage_dirs
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
    has_v2_storage = _v2_storage_ready(paths)
    has_legacy_tables = bool(LEGACY_TABLES.intersection(table_names))

    runtime.log.debug(
        "bb_status environment=%s data_home=%s database=%s initialized=%s "
        "bb_table_count=%s v2_foundation=%s v2_storage=%s legacy_tables=%s",
        paths.environment,
        paths.root,
        paths.database,
        initialized,
        bb_table_count,
        has_v2_foundation,
        has_v2_storage,
        has_legacy_tables,
    )

    click.echo("CLI: bb")
    click.echo(f"Environment: {paths.environment}")
    click.echo(f"Storage layout: {paths.layout}")
    click.echo(f"Data home: {paths.root}")
    click.echo(f"Database: {paths.database}")
    click.echo(f"Initialized: {initialized}")
    click.echo(f"V2 foundation: {_yes_no(has_v2_foundation)}")
    click.echo(f"V2 storage: {_yes_no(has_v2_storage)}")
    click.echo(f"BB tables: {bb_table_count}")
    click.echo(f"Legacy tables: {'present' if has_legacy_tables else 'absent'}")
    if has_v2_storage:
        click.echo(f"Financial canonical: {paths.financial_canonical}")
        click.echo(f"Financial views: {paths.financial_views}")


@main.command("init")
@click.pass_context
def init_command(ctx: click.Context) -> None:
    """Initialize the local BankBuddy v2 app directory and database."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    initialize_database(paths)
    ensure_financial_storage_dirs(paths)
    runtime.log.debug(
        "bb_init home=%s database=%s financial_canonical=%s financial_views=%s",
        paths.root,
        paths.database,
        paths.financial_canonical,
        paths.financial_views,
    )
    click.echo(f"Initialized BankBuddy v2 at {paths.root}")


@main.group()
def documents() -> None:
    """Manage v2 documents."""


@documents.command("list")
@click.pass_context
def documents_list(ctx: click.Context) -> None:
    """List imported v2 documents."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    rows = list_documents(paths)
    render_document_table(rows)


@documents.command("show")
@click.argument("document_id", type=int)
@click.pass_context
def documents_show(ctx: click.Context, document_id: int) -> None:
    """Show one imported v2 document."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    summary = get_document_summary(paths, document_id)
    if summary is None:
        raise click.ClickException(f"Document not found: {document_id}")
    render_document_summary(summary)


@documents.command("import")
@click.option("--dry-run", is_flag=True, help="Plan the import without writes.")
@click.option(
    "--file",
    "file_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Document file to import.",
)
@click.pass_context
def documents_import(
    ctx: click.Context,
    dry_run: bool,
    file_path: Path,
) -> None:
    """Import one document into v2 canonical storage."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        if dry_run:
            plan = plan_document_import(paths, file_path)
            _print_document_import_plan(plan, dry_run=True)
            click.echo("Database changed: no")
            click.echo("Files changed: none")
            return
        result = import_document(paths, file_path)
    except (OSError, DocumentImportError) as exc:
        raise click.ClickException(str(exc)) from exc

    _print_document_import_plan(result.plan, dry_run=False)
    click.echo(f"Document ID: {result.document.document_id}")
    click.echo(f"Document object ID: {result.document_object.document_object_id}")
    click.echo(f"Duplicate: {_yes_no(result.duplicate)}")


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


def _print_document_import_plan(plan, *, dry_run: bool) -> None:
    click.echo(f"Dry run: {_yes_no(dry_run)}")
    click.echo(f"File: {plan.source_path.name}")
    click.echo(f"SHA-256: {plan.file_hash}")
    click.echo(f"Size: {plan.byte_size} bytes")
    click.echo(f"Media type: {plan.media_type}")
    click.echo(f"Canonical object: {plan.canonical_relative_path}")


def render_document_table(rows: list[DocumentSummary]) -> None:
    """Render v2 documents as a compact pretty table."""

    table = [
        [
            str(row.document.document_id),
            row.document.original_file_name,
            row.document.document_status,
            str(row.canonical_object.byte_size)
            if row.canonical_object and row.canonical_object.byte_size is not None
            else "-",
            row.canonical_object.media_type if row.canonical_object else "-",
            row.document.file_hash[:12],
        ]
        for row in rows
    ]
    render_pretty_table(
        ["ID", "File", "Status", "Size", "Media Type", "SHA-256"],
        table,
        align_right={0, 3},
    )


def render_document_summary(summary: DocumentSummary) -> None:
    """Render one v2 document detail view."""

    document = summary.document
    canonical_object = summary.canonical_object
    click.echo(f"Document ID: {document.document_id}")
    click.echo(f"Original file: {document.original_file_name}")
    click.echo(f"SHA-256: {document.file_hash}")
    click.echo(f"Status: {document.document_status}")
    click.echo(f"Type: {_display_value(document.document_type)}")
    click.echo(f"Jurisdiction: {_display_value(document.jurisdiction_code)}")
    click.echo(f"Tax year: {_display_value(document.tax_year)}")
    if canonical_object is None:
        click.echo("Canonical object ID: -")
        click.echo("Canonical object: -")
        return
    click.echo(f"Canonical object ID: {canonical_object.document_object_id}")
    click.echo(f"Canonical object: financial/canonical/{canonical_object.object_key}")
    click.echo(f"Media type: {_display_value(canonical_object.media_type)}")
    click.echo(f"Size: {_display_value(canonical_object.byte_size)} bytes")


def render_pretty_table(
    headers: list[str],
    rows: list[list[str]],
    *,
    align_right: set[int] | None = None,
) -> None:
    """Render a small pretty table with vertical separators."""

    align_right = align_right or set()
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    click.echo(_pretty_row(headers, widths, align_right=set()))
    click.echo("-+-".join("-" * width for width in widths))
    for row in rows:
        click.echo(_pretty_row(row, widths, align_right=align_right))


def _pretty_row(
    values: list[str],
    widths: list[int],
    *,
    align_right: set[int],
) -> str:
    cells = []
    for index, value in enumerate(values):
        width = widths[index]
        if index in align_right:
            cells.append(value.rjust(width))
        else:
            cells.append(value.ljust(width))
    return " | ".join(cells)


def _display_value(value) -> str:
    if value is None:
        return "-"
    return str(value)


def _v2_storage_ready(paths) -> bool:
    return all(
        path.is_dir()
        for path in (
            paths.financial_inbox,
            paths.financial_canonical,
            paths.financial_failed,
            paths.financial_duplicates,
            paths.financial_review,
            paths.financial_views,
            paths.financial_exports,
        )
    )


def runtime_from_context(ctx: click.Context) -> CliRuntime:
    """Return the root bb runtime context."""

    runtime = ctx.find_root().obj
    if not isinstance(runtime, CliRuntime):
        raise click.ClickException("bb runtime context is not active.")
    return runtime
