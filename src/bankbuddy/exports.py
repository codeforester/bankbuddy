"""Export helpers for BankBuddy data."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from bankbuddy.database import initialize_database
from bankbuddy.paths import AppPaths


class ExportFailure(ValueError):
    """Raised when an export cannot proceed."""


def export_sqlite_database(
    paths: AppPaths,
    output_path: Path,
    *,
    force: bool = False,
) -> Path:
    """Export the live SQLite database to a user-selected path."""

    initialize_database(paths)
    resolved_output = output_path.expanduser().resolve()
    resolved_database = paths.database.expanduser().resolve()

    if resolved_output == resolved_database:
        raise ExportFailure("Export output cannot be the live database path.")
    if not resolved_output.parent.is_dir():
        raise ExportFailure(
            f"Export parent directory does not exist: {resolved_output.parent}"
        )
    if resolved_output.is_dir():
        raise ExportFailure(f"Export output is a directory: {resolved_output}")
    if resolved_output.exists():
        if not force:
            raise ExportFailure(
                f"Export output already exists: {resolved_output}. "
                "Use --force to overwrite."
            )
        resolved_output.unlink()

    with sqlite3.connect(resolved_database) as source:
        with sqlite3.connect(resolved_output) as destination:
            source.backup(destination)

    return resolved_output
