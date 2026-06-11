"""SQLite bootstrap helpers."""

from __future__ import annotations

import sqlite3

from bankbuddy.paths import AppPaths, ensure_app_dirs


SCHEMA_MIGRATIONS_SQL = """
create table if not exists schema_migrations (
    version text primary key,
    applied_at text not null default current_timestamp
)
"""


def connect_database(paths: AppPaths) -> sqlite3.Connection:
    """Open a SQLite connection for the resolved app paths."""

    ensure_app_dirs(paths)
    conn = sqlite3.connect(paths.database)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(paths: AppPaths) -> None:
    """Create the app directories and the migration bookkeeping table."""

    with connect_database(paths) as conn:
        conn.execute(SCHEMA_MIGRATIONS_SQL)
        conn.commit()
