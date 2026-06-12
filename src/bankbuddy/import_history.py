"""Import history query helpers."""

from __future__ import annotations

from dataclasses import dataclass

from bankbuddy.database import connect_database, initialize_database
from bankbuddy.paths import AppPaths


@dataclass(frozen=True)
class ImportHistoryRow:
    """An import attempt row prepared for CLI display."""

    attempt_id: int
    file_name: str
    canonical_file_name: str
    processed_path: str | None
    bank_name: str
    status: str
    started_at: str
    finished_at: str | None
    rows_parsed: int
    rows_imported: int
    rows_skipped_duplicate: int
    error_message: str | None


def list_import_history(
    paths: AppPaths,
    *,
    status: str | None = None,
    limit: int = 20,
) -> list[ImportHistoryRow]:
    """Return import attempts ordered newest first."""

    initialize_database(paths)
    conditions: list[str] = []
    parameters: list[object] = []
    if status is not None:
        conditions.append("import_attempts.import_status = ?")
        parameters.append(status)
    parameters.append(limit)

    where_clause = f"where {' and '.join(conditions)}" if conditions else ""
    with connect_database(paths) as conn:
        rows = conn.execute(
            f"""
            select
                import_attempts.attempt_id,
                import_files.file_name,
                coalesce(import_files.canonical_file_name, '-') as canonical_file_name,
                import_files.processed_path,
                coalesce(banks.bank_name, '-') as bank_name,
                import_attempts.import_status,
                import_attempts.started_at,
                import_attempts.finished_at,
                import_attempts.rows_parsed,
                import_attempts.rows_imported,
                import_attempts.rows_skipped_duplicate,
                import_attempts.error_message
            from import_attempts
            join import_files using (file_id)
            left join banks on banks.bank_id = import_attempts.bank_id
            {where_clause}
            order by import_attempts.attempt_id desc
            limit ?
            """,
            parameters,
        ).fetchall()

    return [
        ImportHistoryRow(
            attempt_id=int(row["attempt_id"]),
            file_name=row["file_name"],
            canonical_file_name=row["canonical_file_name"],
            processed_path=row["processed_path"],
            bank_name=row["bank_name"],
            status=row["import_status"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            rows_parsed=int(row["rows_parsed"]),
            rows_imported=int(row["rows_imported"]),
            rows_skipped_duplicate=int(row["rows_skipped_duplicate"]),
            error_message=row["error_message"],
        )
        for row in rows
    ]
