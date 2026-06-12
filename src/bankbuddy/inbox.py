"""Managed inbox import helpers."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from bankbuddy.database import initialize_database
from bankbuddy.imports import ImportFailure
from bankbuddy.imports import import_boa_csv
from bankbuddy.imports import import_boa_pdf
from bankbuddy.paths import AppPaths


@dataclass(frozen=True)
class InboxFileResult:
    """Per-file inbox processing result."""

    file_name: str
    status: str
    message: str
    rows_parsed: int = 0
    rows_imported: int = 0
    rows_skipped_duplicate: int = 0


@dataclass(frozen=True)
class InboxImportSummary:
    """Aggregate inbox processing result."""

    results: list[InboxFileResult]

    @property
    def total_files(self) -> int:
        return len(self.results)

    @property
    def successful_files(self) -> int:
        return sum(1 for result in self.results if result.status == "success")

    @property
    def failed_files(self) -> int:
        return sum(1 for result in self.results if result.status == "failed")

    @property
    def unsupported_files(self) -> int:
        return sum(1 for result in self.results if result.status == "unsupported")


def iter_inbox_files(paths: AppPaths) -> list[Path]:
    """Return visible regular files in the inbox in stable order."""

    if not paths.inbox.exists():
        return []
    return sorted(
        (
            path
            for path in paths.inbox.iterdir()
            if path.is_file() and not path.name.startswith(".")
        ),
        key=lambda path: path.name,
    )


def import_inbox(
    paths: AppPaths,
    *,
    account_id: int,
    logger: logging.Logger | None = None,
) -> InboxImportSummary:
    """Import supported files from the managed inbox for one account."""

    initialize_database(paths)
    results: list[InboxFileResult] = []
    for inbox_file in iter_inbox_files(paths):
        suffix = inbox_file.suffix.lower()
        if suffix not in {".csv", ".pdf"}:
            results.append(
                InboxFileResult(
                    file_name=inbox_file.name,
                    status="unsupported",
                    message=f"Unsupported import file type: {suffix or '(none)'}",
                )
            )
            continue

        try:
            if suffix == ".csv":
                summary = import_boa_csv(
                    paths,
                    inbox_file,
                    account_id=account_id,
                    logger=logger,
                )
            else:
                summary = import_boa_pdf(
                    paths,
                    inbox_file,
                    account_id=account_id,
                    logger=logger,
                )
        except ImportFailure as exc:
            results.append(
                InboxFileResult(
                    file_name=inbox_file.name,
                    status="failed",
                    message=str(exc),
                )
            )
            continue

        inbox_file.unlink()
        results.append(
            InboxFileResult(
                file_name=inbox_file.name,
                status="success",
                message="Imported",
                rows_parsed=summary.rows_parsed,
                rows_imported=summary.rows_imported,
                rows_skipped_duplicate=summary.rows_skipped_duplicate,
            )
        )

    return InboxImportSummary(results=results)
