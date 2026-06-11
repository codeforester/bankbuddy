from click.testing import CliRunner

from bankbuddy.cli import main


def test_cli_version() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "bank-buddy, version 0.1.0" in result.output


def test_status_reports_uninitialized_database(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["status"],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert f"Home: {tmp_path}" in result.output
    assert f"Database: {tmp_path / 'bankbuddy.sqlite3'}" in result.output
    assert "Initialized: no" in result.output


def test_init_creates_database(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["init"],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "Initialized Bank Buddy" in result.output
    assert (tmp_path / "bankbuddy.sqlite3").is_file()
