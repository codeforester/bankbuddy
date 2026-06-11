"""SQLite bootstrap helpers."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import sqlite3

from bankbuddy.paths import AppPaths, ensure_app_dirs


MIGRATIONS_PACKAGE = "bankbuddy.migrations"
SCHEMA_MIGRATIONS_SQL = """
create table if not exists schema_migrations (
    version text primary key,
    applied_at text not null default current_timestamp
)
"""


@dataclass(frozen=True)
class Migration:
    """A packaged SQL migration."""

    version: str
    name: str
    sql: str


def connect_database(paths: AppPaths) -> sqlite3.Connection:
    """Open a SQLite connection for the resolved app paths."""

    ensure_app_dirs(paths)
    conn = sqlite3.connect(paths.database)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


def iter_migrations() -> list[Migration]:
    """Return packaged SQL migrations in version order."""

    migration_root = resources.files(MIGRATIONS_PACKAGE)
    migrations: list[Migration] = []
    for migration_file in sorted(migration_root.iterdir(), key=lambda path: path.name):
        if migration_file.name.endswith(".sql"):
            version = migration_file.name.removesuffix(".sql")
            migrations.append(
                Migration(
                    version=version,
                    name=migration_file.name,
                    sql=migration_file.read_text(encoding="utf-8"),
                )
            )
    return migrations


def _sql_text_literal(value: str) -> str:
    """Return a single-quoted SQLite text literal for internal migration SQL."""

    return "'" + value.replace("'", "''") + "'"


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending packaged SQL migrations."""

    conn.execute(SCHEMA_MIGRATIONS_SQL)
    conn.commit()
    applied_versions = {
        row["version"] for row in conn.execute("select version from schema_migrations")
    }

    for migration in iter_migrations():
        if migration.version in applied_versions:
            continue
        migration_script = "\n".join(
            [
                "begin;",
                migration.sql.rstrip(),
                "insert into schema_migrations (version) values "
                f"({_sql_text_literal(migration.version)});",
                "commit;",
            ]
        )
        try:
            conn.executescript(migration_script)
        except sqlite3.Error:
            conn.rollback()
            raise
        applied_versions.add(migration.version)


def initialize_database(paths: AppPaths) -> None:
    """Create the app directories and apply all database migrations."""

    with connect_database(paths) as conn:
        apply_migrations(conn)
        conn.commit()
