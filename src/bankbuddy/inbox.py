"""Managed inbox import helpers."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

import bankbuddy.imports as statement_imports
from bankbuddy.database import connect_database
from bankbuddy.database import initialize_database
from bankbuddy.import_files import archive_duplicate_statement_file
from bankbuddy.import_files import plan_duplicate_statement_path
from bankbuddy.imports import ImportFailure
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
    processed_path: str | None = None
    duplicate_path: str | None = None


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

    @property
    def duplicate_files(self) -> int:
        return sum(1 for result in self.results if result.status == "duplicate")


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
    account_id: int | None = None,
    dry_run: bool = False,
    logger: logging.Logger | None = None,
) -> InboxImportSummary:
    """Import supported files from the managed inbox for one account."""

    initialize_database(paths)
    results: list[InboxFileResult] = []
    for inbox_file in iter_inbox_files(paths):
        suffix = inbox_file.suffix.lower()
        if suffix not in {".csv", ".pdf", ".xls"}:
            results.append(
                InboxFileResult(
                    file_name=inbox_file.name,
                    status="unsupported",
                    message=f"Unsupported import file type: {suffix or '(none)'}",
                )
            )
            continue

        file_hash = statement_imports.hash_file(inbox_file)
        duplicate = statement_imports.find_successful_import_by_hash(paths, file_hash)
        if duplicate is not None:
            if dry_run:
                duplicate_path = plan_duplicate_statement_path(
                    paths,
                    bank_name=duplicate.bank_name,
                    statement_end_date=duplicate.statement_end_date,
                    canonical_file_name=duplicate.canonical_file_name,
                )
                message = f"Would skip duplicate of {duplicate.processed_path}"
            else:
                duplicate_path = archive_duplicate_statement_file(
                    paths,
                    source_path=inbox_file,
                    bank_name=duplicate.bank_name,
                    statement_end_date=duplicate.statement_end_date,
                    canonical_file_name=duplicate.canonical_file_name,
                )
                statement_imports.record_duplicate_import(
                    paths,
                    duplicate,
                    duplicate_path=duplicate_path,
                )
                inbox_file.unlink()
                message = (
                    f"Duplicate of {duplicate.processed_path}; "
                    f"preserved at {duplicate_path}"
                )
            results.append(
                InboxFileResult(
                    file_name=inbox_file.name,
                    status="duplicate",
                    message=message,
                    processed_path=duplicate.processed_path,
                    duplicate_path=duplicate_path,
                )
            )
            continue

        try:
            if suffix == ".csv":
                if account_id is None:
                    message = (
                        "CSV inbox import requires --account-id because the "
                        "current CSV parser has no reliable account metadata."
                    )
                    if not dry_run:
                        statement_imports.record_failed_import(
                            paths,
                            inbox_file,
                            source_format="boa_csv",
                            error_message=message,
                        )
                    raise ImportFailure(
                        message
                    )
                if dry_run:
                    import_result = statement_imports.plan_boa_csv_import(
                        paths,
                        inbox_file,
                        account_id=account_id,
                        logger=logger,
                    )
                else:
                    import_result = statement_imports.import_boa_csv(
                        paths,
                        inbox_file,
                        account_id=account_id,
                        logger=logger,
                    )
            elif suffix == ".pdf":
                resolved_account_id = account_id
                extracted_text: str | None = None
                if resolved_account_id is None:
                    extracted_text = statement_imports.extract_pdf_text(inbox_file)
                    pdf_account_number = statement_imports.extract_boa_pdf_account_number(
                        extracted_text
                    )
                    resolved_account_id = account_id_for_boa_pdf_account_number(
                        paths,
                        pdf_account_number,
                    )
                    if resolved_account_id is None:
                        account_suffix = statement_imports.account_number_suffix(
                            pdf_account_number
                        )
                        message = (
                            "No configured account matches Bank of America PDF "
                            f"account ending {account_suffix}."
                        )
                        if not dry_run:
                            statement_imports.record_failed_import(
                                paths,
                                inbox_file,
                                source_format="boa_pdf",
                                error_message=message,
                            )
                        raise ImportFailure(
                            message
                        )

                if dry_run:
                    import_result = statement_imports.plan_boa_pdf_import(
                        paths,
                        inbox_file,
                        account_id=resolved_account_id,
                        extracted_text=extracted_text,
                        logger=logger,
                    )
                else:
                    import_result = statement_imports.import_boa_pdf(
                        paths,
                        inbox_file,
                        account_id=resolved_account_id,
                        extracted_text=extracted_text,
                        logger=logger,
                    )
            else:
                parsed_statement, source_format = statement_imports.parse_xls_statement(
                    inbox_file
                )
                resolved_account_id = account_id
                if resolved_account_id is None:
                    resolved_account_id = account_id_for_parsed_statement(
                        paths,
                        parsed_statement,
                    )
                    if resolved_account_id is None:
                        account_suffix = statement_imports.account_number_suffix(
                            parsed_statement.account_number
                        )
                        message = (
                            "No configured account matches "
                            f"{parsed_statement.bank_name} XLS account ending "
                            f"{account_suffix}."
                        )
                        if not dry_run:
                            statement_imports.record_failed_import(
                                paths,
                                inbox_file,
                                source_format=source_format,
                                error_message=message,
                            )
                        raise ImportFailure(message)

                if dry_run:
                    import_result = statement_imports.plan_parsed_statement_import(
                        paths,
                        inbox_file,
                        account_id=resolved_account_id,
                        parsed_statement=parsed_statement,
                        source_format=source_format,
                        import_label="XLS",
                        logger=logger,
                    )
                else:
                    import_result = statement_imports.import_parsed_statement(
                        paths,
                        inbox_file,
                        account_id=resolved_account_id,
                        parsed_statement=parsed_statement,
                        source_format=source_format,
                        import_label="XLS",
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

        if not dry_run:
            inbox_file.unlink()
        results.append(
            InboxFileResult(
                file_name=inbox_file.name,
                status="success",
                message="Would import" if dry_run else "Imported",
                rows_parsed=import_result.rows_parsed,
                rows_imported=import_result.rows_would_import
                if dry_run
                else import_result.rows_imported,
                rows_skipped_duplicate=import_result.rows_already_present
                if dry_run
                else import_result.rows_skipped_duplicate,
                processed_path=import_result.processed_path if dry_run else None,
            )
        )

    return InboxImportSummary(results=results)


def account_id_for_boa_pdf_account_number(
    paths: AppPaths,
    account_number: str,
) -> int | None:
    """Return the configured BOA USD account id for a normalized PDF account number."""

    normalized_account_number = statement_imports.normalize_account_number(account_number)
    with connect_database(paths) as conn:
        rows = conn.execute(
            """
            select
                accounts.account_id,
                accounts.account_number
            from accounts
            join banks using (bank_id)
            where banks.bank_name = ?
              and accounts.currency = ?
            order by accounts.account_id
            """,
            ("Bank of America", "USD"),
        ).fetchall()

    matches = [
        int(row["account_id"])
        for row in rows
        if statement_imports.normalize_account_number(row["account_number"])
        == normalized_account_number
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def account_id_for_parsed_statement(
    paths: AppPaths,
    parsed_statement: statement_imports.ParsedStatement,
) -> int | None:
    """Return the configured account id matching parsed statement metadata."""

    normalized_account_number = statement_imports.normalize_account_number(
        parsed_statement.account_number
    )
    with connect_database(paths) as conn:
        rows = conn.execute(
            """
            select
                accounts.account_id,
                accounts.account_number
            from accounts
            join banks using (bank_id)
            where banks.bank_name = ?
              and accounts.currency = ?
            order by accounts.account_id
            """,
            (parsed_statement.bank_name, parsed_statement.currency),
        ).fetchall()

    matches = [
        int(row["account_id"])
        for row in rows
        if statement_imports.normalize_account_number(row["account_number"])
        == normalized_account_number
    ]
    if len(matches) != 1:
        return None
    return matches[0]
