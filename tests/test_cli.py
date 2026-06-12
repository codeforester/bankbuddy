from click.testing import CliRunner

from bankbuddy.database import connect_database
from bankbuddy.cli import main
from bankbuddy.paths import resolve_app_paths


def test_cli_version() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "bank-buddy, version 0.1.0" in result.output


def test_cli_help_includes_base_runtime_options() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    for option in (
        "-v, --debug",
        "--environment",
        "--config",
        "--keep-temp",
        "--log-file",
    ):
        assert option in result.output


def test_config_can_enable_debug_logging(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "environment: qa\nlog_level: debug\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        ["--config", str(config_path), "status"],
        env={
            "BANKBUDDY_HOME": str(tmp_path / "home"),
            "BASE_CACHE_DIR": str(tmp_path / "cache"),
        },
    )

    assert result.exit_code == 0
    assert "Home:" in result.stdout
    assert "DEBUG" in result.stderr
    assert "environment=qa" in result.stderr


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


def test_account_add_creates_bank_and_account(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
            "--statement-ref",
            "6789",
            "--display-name",
            "Everyday Checking",
        ],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "Added account 1 for Bank of America" in result.output

    paths = resolve_app_paths(tmp_path)
    with connect_database(paths) as conn:
        account = conn.execute(
            """
            select
                banks.bank_name,
                banks.country,
                banks.default_currency,
                accounts.account_number,
                accounts.account_type,
                accounts.currency,
                accounts.statement_account_ref,
                accounts.display_name
            from accounts
            join banks using (bank_id)
            """
        ).fetchone()

    assert dict(account) == {
        "bank_name": "Bank of America",
        "country": "US",
        "default_currency": "USD",
        "account_number": "123456789",
        "account_type": "checking",
        "currency": "USD",
        "statement_account_ref": "6789",
        "display_name": "Everyday Checking",
    }


def test_account_add_rejects_duplicate_bank_account(tmp_path) -> None:
    runner = CliRunner()
    args = [
        "account",
        "add",
        "--bank",
        "Bank of America",
        "--country",
        "US",
        "--account-number",
        "123456789",
        "--type",
        "checking",
        "--currency",
        "USD",
    ]

    first = runner.invoke(main, args, env={"BANKBUDDY_HOME": str(tmp_path)})
    second = runner.invoke(main, args, env={"BANKBUDDY_HOME": str(tmp_path)})

    assert first.exit_code == 0
    assert second.exit_code == 1
    assert "Account already exists for Bank of America" in second.output


def test_account_list_outputs_configured_accounts_with_last_four(tmp_path) -> None:
    runner = CliRunner()
    add_result = runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
            "--display-name",
            "Everyday Checking",
        ],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    list_result = runner.invoke(
        main,
        ["account", "list"],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert add_result.exit_code == 0
    assert list_result.exit_code == 0
    assert "1  Bank of America  Everyday Checking  checking  USD  ...6789" in (
        list_result.output
    )
    assert "123456789" not in list_result.output
