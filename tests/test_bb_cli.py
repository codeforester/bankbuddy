from click.testing import CliRunner

from bankbuddy.bb.cli import main
from bankbuddy.database import initialize_database
from bankbuddy.paths import resolve_app_paths


def test_bb_cli_version() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "bb, version 0.1.0" in result.output


def test_bb_status_reports_environment_data_home_and_v2_schema(tmp_path) -> None:
    initialize_database(resolve_app_paths(tmp_path))

    result = CliRunner().invoke(
        main,
        ["status"],
        env={
            "BANKBUDDY_HOME": str(tmp_path),
            "BANKBUDDY_ENV": "dev",
        },
    )

    assert result.exit_code == 0
    assert "CLI: bb" in result.output
    assert "Environment: dev" in result.output
    assert f"Data home: {tmp_path}" in result.output
    assert f"Database: {tmp_path / 'database' / 'bankbuddy.sqlite3'}" in result.output
    assert "Initialized: yes" in result.output
    assert "V2 foundation: yes" in result.output
    assert "BB tables: 20" in result.output
    assert "Legacy tables: present" in result.output


def test_bb_status_reports_missing_v2_schema(tmp_path) -> None:
    result = CliRunner().invoke(main, ["status"], env={"BANKBUDDY_HOME": str(tmp_path)})

    assert result.exit_code == 0
    assert "CLI: bb" in result.output
    assert "Initialized: no" in result.output
    assert "V2 foundation: no" in result.output
    assert "BB tables: 0" in result.output
