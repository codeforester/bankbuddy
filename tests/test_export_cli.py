import sqlite3

from click.testing import CliRunner

from bankbuddy.cli import main


def test_export_sqlite_command_writes_database_and_warning(tmp_path) -> None:
    output_path = tmp_path / "backup.sqlite3"

    result = CliRunner().invoke(
        main,
        ["export", "sqlite", "--output", str(output_path)],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert f"Exported SQLite database to {output_path}" in result.output
    assert "contains sensitive financial data and actual account numbers" in (
        result.output
    )
    with sqlite3.connect(output_path) as conn:
        row = conn.execute(
            "select name from sqlite_master where type = 'table' and name = ?",
            ("schema_migrations",),
        ).fetchone()
    assert row == ("schema_migrations",)


def test_export_sqlite_command_refuses_existing_output_without_force(tmp_path) -> None:
    output_path = tmp_path / "backup.sqlite3"
    output_path.write_text("do not overwrite", encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["export", "sqlite", "--output", str(output_path)],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "already exists" in result.output
    assert output_path.read_text(encoding="utf-8") == "do not overwrite"


def test_export_sqlite_command_force_overwrites_existing_output(tmp_path) -> None:
    output_path = tmp_path / "backup.sqlite3"
    output_path.write_text("overwrite", encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["export", "sqlite", "--output", str(output_path), "--force"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    with sqlite3.connect(output_path) as conn:
        row = conn.execute(
            "select name from sqlite_master where type = 'table' and name = ?",
            ("schema_migrations",),
        ).fetchone()
    assert row == ("schema_migrations",)
