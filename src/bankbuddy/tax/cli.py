"""TaxBuddy command line interface."""

from __future__ import annotations

from pathlib import Path

import click

from bankbuddy import __version__
from bankbuddy.paths import resolve_app_paths
from bankbuddy.runtime import CliRuntime
from bankbuddy.runtime import RuntimeConfigError
from bankbuddy.runtime import create_runtime
from bankbuddy.tax.documents import get_tax_document
from bankbuddy.tax.documents import import_tax_document
from bankbuddy.tax.documents import list_tax_documents
from bankbuddy.tax.documents import plan_tax_document_import
from bankbuddy.tax.documents import TaxDocumentRow
from bankbuddy.tax.documents import TaxImportFailure
from bankbuddy.tax.documents import TaxImportPlan
from bankbuddy.tax.documents import TaxImportSummary


@click.group(
    name="taxbuddy",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="taxbuddy")
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
    """Local-first tax document readiness."""

    try:
        runtime = create_runtime(
            debug=debug,
            environment=environment,
            config_path=config_path,
            keep_temp=keep_temp,
            log_file=log_file,
            cli_name="taxbuddy",
        )
    except (OSError, RuntimeConfigError) as exc:
        raise click.ClickException(str(exc)) from exc

    ctx.obj = runtime
    ctx.call_on_close(runtime.cleanup)


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show the local TaxBuddy app state."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    initialized = "yes" if paths.database.exists() else "no"
    runtime.log.debug(
        "tax_status environment=%s data_home=%s database=%s initialized=%s",
        paths.environment,
        paths.root,
        paths.database,
        initialized,
    )

    click.echo(f"Environment: {paths.environment}")
    click.echo(f"Data home: {paths.root}")
    click.echo(f"Database: {paths.database}")
    click.echo(f"Tax inbox: {paths.tax_inbox}")
    click.echo(f"Tax processed: {paths.tax_processed}")
    click.echo(f"Initialized: {initialized}")


@main.group("import", invoke_without_command=True, no_args_is_help=False)
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Tax document file to import.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview parser, duplicate, and archive actions without writing changes.",
)
@click.pass_context
def import_command(
    ctx: click.Context,
    file_path: Path | None,
    dry_run: bool,
) -> None:
    """Import tax documents."""

    ctx.obj.import_dry_run = dry_run
    if ctx.invoked_subcommand is not None:
        return
    if file_path is None:
        raise click.UsageError("Missing option '--file' or subcommand 'inbox'.")

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        if dry_run:
            plan = plan_tax_document_import(paths, file_path)
            print_tax_import_plan(plan)
        else:
            summary = import_tax_document(paths, file_path)
            print_tax_import_summary(summary)
    except TaxImportFailure as exc:
        runtime.log.debug("tax_import_failed reason=%s", exc)
        raise click.ClickException(str(exc)) from exc


@import_command.command("inbox")
@click.pass_context
def import_inbox_command(ctx: click.Context) -> None:
    """Import tax documents from the managed tax inbox."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    dry_run = bool(getattr(ctx.obj, "import_dry_run", False))
    files = iter_tax_inbox_files(paths.tax_inbox)
    if not files:
        click.echo("No tax inbox files found.")
        return

    results: list[tuple[str, Path, TaxImportPlan | TaxImportSummary | str]] = []
    for file_path in files:
        try:
            if dry_run:
                result = plan_tax_document_import(paths, file_path)
            else:
                result = import_tax_document(paths, file_path)
                if not result.duplicate:
                    file_path.unlink()
            results.append(("duplicate" if result.duplicate else "success", file_path, result))
        except TaxImportFailure as exc:
            results.append(("failed", file_path, str(exc)))

    planned_imports = sum(
        1 for status, _path, result in results if status == "success" and not result.duplicate
    )
    planned_duplicates = sum(1 for status, _path, _result in results if status == "duplicate")
    failed = sum(1 for status, _path, _result in results if status == "failed")

    if dry_run:
        click.echo("Dry run: yes")
        click.echo(f"Inbox files: {len(files)}")
        click.echo(f"Planned imports: {planned_imports}")
        click.echo(f"Planned duplicates: {planned_duplicates}")
        click.echo(f"Failed: {failed}")
    else:
        click.echo(f"Inbox files: {len(files)}")
        click.echo(f"Successful: {planned_imports}")
        click.echo(f"Duplicates: {planned_duplicates}")
        click.echo(f"Failed: {failed}")

    for status, file_path, result in results:
        if isinstance(result, str):
            click.echo(f"failed  {file_path.name}  {result}")
        elif status == "duplicate":
            prefix = "would-skip-duplicate" if dry_run else "duplicate"
            click.echo(
                f"{prefix}  {file_path.name}  document-id={result.existing_document_id or result.tax_document_id} "
                f"canonical={result.processed_path}"
            )
        else:
            prefix = "would-import" if dry_run else "success"
            click.echo(
                f"{prefix}  {file_path.name}  type={result.document_type} "
                f"year={result.tax_year} canonical={result.processed_path}"
            )


@main.group()
def docs() -> None:
    """Inspect indexed tax documents."""


@docs.command("list")
@click.option("--year", type=int, help="Filter by tax year.")
@click.option("--type", "document_type", help="Filter by document type.")
@click.pass_context
def docs_list(
    ctx: click.Context,
    year: int | None,
    document_type: str | None,
) -> None:
    """List indexed tax documents."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    rows = list_tax_documents(paths, year=year, document_type=document_type)
    if not rows:
        click.echo("No tax documents found.")
        return
    render_tax_document_table(rows)


@docs.command("show")
@click.argument("tax_document_id", type=int)
@click.pass_context
def docs_show(ctx: click.Context, tax_document_id: int) -> None:
    """Show one indexed tax document."""

    runtime = runtime_from_context(ctx)
    paths = resolve_app_paths(environment=runtime.environment)
    try:
        row = get_tax_document(paths, tax_document_id)
    except TaxImportFailure as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Document ID: {row.tax_document_id}")
    click.echo(f"Original: {row.original_file_name}")
    click.echo(f"Canonical: {row.canonical_file_name}")
    click.echo(f"Processed: {row.processed_path}")
    click.echo(f"Type: {row.document_type}")
    click.echo(f"Jurisdiction: {row.jurisdiction}")
    click.echo(f"Tax year: {row.tax_year}")
    click.echo(f"Source: {row.source_entity}")
    click.echo(f"Account: {row.account_ref or '-'}")
    click.echo(f"Person: {row.person_label or '-'}")
    click.echo(f"Imported: {row.imported_at}")


def print_tax_import_plan(plan: TaxImportPlan) -> None:
    """Print a dry-run tax import plan."""

    click.echo("Dry run: yes")
    click.echo(f"File: {plan.file_name}")
    click.echo(f"Document type: {plan.document_type}")
    click.echo(f"Jurisdiction: {plan.jurisdiction}")
    click.echo(f"Tax year: {plan.tax_year}")
    click.echo(f"Source: {plan.source_entity}")
    click.echo(f"Account: {plan.account_ref or '-'}")
    click.echo(f"Processed path: {plan.processed_path}")
    click.echo(f"Duplicate: {'yes' if plan.duplicate else 'no'}")
    if plan.existing_document_id is not None:
        click.echo(f"Existing document ID: {plan.existing_document_id}")
    click.echo("Database changed: no")
    click.echo("Files changed: none")


def print_tax_import_summary(summary: TaxImportSummary) -> None:
    """Print a real tax import summary."""

    click.echo(f"File: {summary.file_name}")
    click.echo(f"Document ID: {summary.tax_document_id}")
    click.echo(f"Document type: {summary.document_type}")
    click.echo(f"Jurisdiction: {summary.jurisdiction}")
    click.echo(f"Tax year: {summary.tax_year}")
    click.echo(f"Source: {summary.source_entity}")
    click.echo(f"Account: {summary.account_ref or '-'}")
    click.echo(f"Processed path: {summary.processed_path}")
    click.echo(f"Duplicate: {'yes' if summary.duplicate else 'no'}")


def render_tax_document_table(rows: list[TaxDocumentRow]) -> None:
    """Render indexed tax documents as an aligned table."""

    table = [
        [
            str(row.tax_document_id),
            str(row.tax_year),
            row.document_type,
            row.jurisdiction,
            row.source_entity,
            row.account_ref or "-",
        ]
        for row in rows
    ]
    render_pretty_table(
        ["ID", "Year", "Type", "Jurisdiction", "Source", "Account"],
        table,
        align_right={0, 1},
    )


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
        if index in align_right:
            cells.append(value.rjust(widths[index]))
        else:
            cells.append(value.ljust(widths[index]))
    return " | ".join(cells)


def iter_tax_inbox_files(inbox_path: Path) -> list[Path]:
    """Return visible regular files in the tax inbox."""

    if not inbox_path.exists():
        return []
    return sorted(
        path
        for path in inbox_path.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )


def runtime_from_context(ctx: click.Context) -> CliRuntime:
    """Return the active TaxBuddy runtime from Click context."""

    runtime = ctx.obj
    if not isinstance(runtime, CliRuntime):
        raise click.ClickException("Internal error: missing CLI runtime.")
    return runtime
