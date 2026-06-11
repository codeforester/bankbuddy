import sqlite3

from bankbuddy.database import initialize_database
from bankbuddy.paths import resolve_app_paths


def test_initialize_database_creates_directories_and_schema_table(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)

    assert paths.inbox.is_dir()
    assert paths.processed.is_dir()
    assert paths.exports.is_dir()
    assert paths.database.is_file()

    with sqlite3.connect(paths.database) as conn:
        row = conn.execute(
            "select name from sqlite_master where type = 'table' and name = 'schema_migrations'"
        ).fetchone()

    assert row == ("schema_migrations",)
