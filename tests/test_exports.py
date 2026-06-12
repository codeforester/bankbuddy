import sqlite3

import pytest

from bankbuddy.database import initialize_database
from bankbuddy.exports import ExportFailure
from bankbuddy.exports import export_sqlite_database
from bankbuddy.paths import resolve_app_paths


def test_export_sqlite_database_writes_backup_file(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    initialize_database(paths)
    output_path = tmp_path / "backup.sqlite3"

    result = export_sqlite_database(paths, output_path)

    assert result == output_path
    assert output_path.is_file()
    with sqlite3.connect(output_path) as conn:
        row = conn.execute(
            "select name from sqlite_master where type = 'table' and name = ?",
            ("schema_migrations",),
        ).fetchone()
    assert row == ("schema_migrations",)


def test_export_sqlite_database_refuses_existing_file_without_force(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    output_path = tmp_path / "backup.sqlite3"
    output_path.write_text("do not replace", encoding="utf-8")

    with pytest.raises(ExportFailure, match="already exists"):
        export_sqlite_database(paths, output_path)

    assert output_path.read_text(encoding="utf-8") == "do not replace"


def test_export_sqlite_database_force_overwrites_existing_file(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    output_path = tmp_path / "backup.sqlite3"
    output_path.write_text("replace me", encoding="utf-8")

    export_sqlite_database(paths, output_path, force=True)

    with sqlite3.connect(output_path) as conn:
        row = conn.execute(
            "select name from sqlite_master where type = 'table' and name = ?",
            ("schema_migrations",),
        ).fetchone()
    assert row == ("schema_migrations",)


def test_export_sqlite_database_requires_existing_parent(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    output_path = tmp_path / "missing" / "backup.sqlite3"

    with pytest.raises(ExportFailure, match="parent directory does not exist"):
        export_sqlite_database(paths, output_path)


def test_export_sqlite_database_refuses_source_database_path(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    initialize_database(paths)

    with pytest.raises(ExportFailure, match="cannot be the live database"):
        export_sqlite_database(paths, paths.database, force=True)
