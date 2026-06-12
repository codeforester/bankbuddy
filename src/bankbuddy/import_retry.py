"""Retry helpers for failed statement imports."""

from __future__ import annotations

import logging
from pathlib import Path
import sqlite3

from bankbuddy.database import connect_database, initialize_database
from bankbuddy.imports import ImportFailure
from bankbuddy.imports import ImportSummary
from bankbuddy.imports import account_number_suffix
from bankbuddy.imports import extract_boa_pdf_account_number
from bankbuddy.imports import extract_pdf_text
from bankbuddy.imports import import_boa_csv
from bankbuddy.imports import import_boa_pdf
from bankbuddy.imports import normalize_account_number
from bankbuddy.paths import AppPaths


class RetryFailure(ValueError):
    """Raised when a failed import attempt cannot be retried."""


def retry_import_attempt(
    paths: AppPaths,
    attempt_id: int,
    *,
    account_id: int | None = None,
    logger: logging.Logger | None = None,
) -> ImportSummary:
    """Retry a failed import attempt by creating a new import attempt."""

    initialize_database(paths)
    attempt = retry_attempt_row(paths, attempt_id)
    if attempt is None:
        raise RetryFailure(f"Import attempt {attempt_id} was not found.")
    if attempt["import_status"] != "failed":
        raise RetryFailure("Only failed import attempts can be retried.")

    retry_path = retry_source_path(paths, attempt, attempt_id)
    source_format = attempt["source_format"]
    retry_account_id = account_id if account_id is not None else attempt["account_id"]

    if source_format == "boa_csv":
        if retry_account_id is None:
            raise RetryFailure("Retrying a Bank of America CSV import requires --account-id.")
        return import_boa_csv(
            paths,
            retry_path,
            account_id=int(retry_account_id),
            logger=logger,
        )

    if source_format == "boa_pdf":
        extracted_text: str | None = None
        if retry_account_id is None:
            extracted_text = extract_pdf_text(retry_path)
            pdf_account_number = extract_boa_pdf_account_number(extracted_text)
            retry_account_id = account_id_for_boa_pdf_account_number(
                paths,
                pdf_account_number,
            )
            if retry_account_id is None:
                account_suffix = account_number_suffix(pdf_account_number)
                raise RetryFailure(
                    "No configured account matches Bank of America PDF "
                    f"account ending {account_suffix}."
                )
        return import_boa_pdf(
            paths,
            retry_path,
            account_id=int(retry_account_id),
            extracted_text=extracted_text,
            logger=logger,
        )

    raise RetryFailure(
        f"Import attempt {attempt_id} has unsupported source format: "
        f"{source_format or '(missing)'}."
    )


def retry_attempt_row(paths: AppPaths, attempt_id: int) -> sqlite3.Row | None:
    """Return the failed-attempt metadata needed for retry."""

    with connect_database(paths) as conn:
        return conn.execute(
            """
            select
                import_attempts.attempt_id,
                import_attempts.import_status,
                import_attempts.account_id,
                import_files.file_name,
                import_files.source_path,
                import_files.processed_path,
                import_files.source_format
            from import_attempts
            join import_files using (file_id)
            where import_attempts.attempt_id = ?
            """,
            (attempt_id,),
        ).fetchone()


def retry_source_path(
    paths: AppPaths,
    attempt: sqlite3.Row,
    attempt_id: int,
) -> Path:
    """Return an existing source path for retry."""

    source_path = attempt["source_path"]
    if source_path:
        path = Path(source_path)
        if path.is_file():
            return path

    processed_path = attempt["processed_path"]
    if processed_path:
        path = paths.root / processed_path
        if path.is_file():
            return path

    raise RetryFailure(f"Source file for attempt {attempt_id} is no longer available.")


def account_id_for_boa_pdf_account_number(
    paths: AppPaths,
    account_number: str,
) -> int | None:
    """Return the configured BOA USD account id for a normalized PDF account number."""

    normalized_account_number = normalize_account_number(account_number)
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
        if normalize_account_number(row["account_number"]) == normalized_account_number
    ]
    if len(matches) != 1:
        return None
    return matches[0]
