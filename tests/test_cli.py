from click.testing import CliRunner

from bankbuddy.database import connect_database
from bankbuddy.cli import main
from bankbuddy.paths import resolve_app_paths


def test_cli_version() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "bankbuddy, version 0.1.0" in result.output


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
    assert "Environment: qa" in result.stdout
    assert "Data home:" in result.stdout
    assert "DEBUG" in result.stderr
    assert "environment=qa" in result.stderr


def test_status_reports_environment_and_data_home(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["status"],
        env={
            "BANKBUDDY_HOME": str(tmp_path / "home"),
            "BANKBUDDY_ENV": "dev",
        },
    )

    assert result.exit_code == 0
    assert "Environment: dev" in result.output
    assert f"Data home: {tmp_path / 'home'}" in result.output
    assert f"Database: {tmp_path / 'home' / 'bankbuddy.sqlite3'}" in result.output


def test_status_environment_option_selects_data_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = CliRunner().invoke(main, ["--environment", "dev", "status"], env={})

    assert result.exit_code == 0
    assert "Environment: dev" in result.output
    assert f"Data home: {tmp_path / 'BankBuddy-dev'}" in result.output
    assert f"Database: {tmp_path / 'BankBuddy-dev' / 'bankbuddy.sqlite3'}" in result.output


def test_status_ignores_base_cli_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = CliRunner().invoke(
        main,
        ["status"],
        env={"BASE_CLI_ENVIRONMENT": "qa"},
    )

    assert result.exit_code == 0
    assert "Environment: prod" in result.output
    assert f"Data home: {tmp_path / 'BankBuddy'}" in result.output


def test_status_reports_uninitialized_database(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["status"],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "Environment: prod" in result.output
    assert f"Data home: {tmp_path}" in result.output
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


def test_account_add_normalizes_country_alias(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "ICICI Bank",
            "--country",
            "India",
            "--account-number",
            "123456789",
            "--type",
            "savings",
            "--currency",
            "INR",
        ],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert result.exit_code == 0

    paths = resolve_app_paths(tmp_path)
    with connect_database(paths) as conn:
        country = conn.execute("select country from banks").fetchone()["country"]

    assert country == "IN"


def test_account_add_rejects_unknown_country(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Unknown Bank",
            "--country",
            "Atlantis",
            "--account-number",
            "123456789",
            "--type",
            "savings",
            "--currency",
            "USD",
        ],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert result.exit_code == 1
    assert "Unsupported country" in result.output


def test_account_add_rejects_existing_bank_country_mismatch(tmp_path) -> None:
    runner = CliRunner()
    first = runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Example Bank",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )
    second = runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Example Bank",
            "--country",
            "IN",
            "--account-number",
            "987654321",
            "--type",
            "savings",
            "--currency",
            "INR",
        ],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert first.exit_code == 0
    assert second.exit_code == 1
    assert "already configured for country US" in second.output

    paths = resolve_app_paths(tmp_path)
    with connect_database(paths) as conn:
        country = conn.execute("select country from banks").fetchone()["country"]

    assert country == "US"


def test_account_add_help_hides_statement_ref_from_normal_usage() -> None:
    result = CliRunner().invoke(main, ["account", "add", "--help"])

    assert result.exit_code == 0
    assert "--country TEXT" in result.output
    assert "ISO 3166-1 alpha-2 country code" in result.output
    assert "--statement-ref" not in result.output


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
    assert "ID | Bank            | Name              | Type     | Currency | Account" in (
        list_result.output
    )
    assert " 1 | Bank of America | Everyday Checking | checking | USD      | ...6789" in (
        list_result.output
    )
    assert "123456789" not in list_result.output


def test_account_summary_outputs_latest_balance_snapshot(tmp_path) -> None:
    runner = CliRunner()
    add_result = runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "ICICI Bank",
            "--country",
            "IN",
            "--account-number",
            "166601075148",
            "--type",
            "savings",
            "--currency",
            "INR",
            "--display-name",
            "ICICI Joint NRO",
        ],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )
    paths = resolve_app_paths(tmp_path)
    with connect_database(paths) as conn:
        cursor = conn.execute(
            """
            insert into import_files (
                file_name,
                file_hash,
                canonical_file_name,
                processed_path
            ) values (?, ?, ?, ?)
            """,
            (
                "ICICI NRO 2025.xls",
                "hash",
                "icici-bank_5148_2025-01-01_2025-12-31.xls",
                "processed/icici-bank/2025/12/"
                "icici-bank_5148_2025-01-01_2025-12-31.xls",
            ),
        )
        conn.execute(
            """
            update accounts
            set latest_balance_minor_units = ?,
                latest_balance_currency = ?,
                latest_balance_as_of_date = ?,
                latest_balance_source_file_id = ?
            where account_id = 1
            """,
            (
                2405025,
                "INR",
                "2025-12-31",
                cursor.lastrowid,
            ),
        )
        conn.commit()

    summary_result = runner.invoke(
        main,
        ["account", "summary"],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert add_result.exit_code == 0
    assert summary_result.exit_code == 0
    assert "ID | Bank       | Name            | Type" in summary_result.output
    assert "ICICI Bank" in summary_result.output
    assert "ICICI Joint NRO" in summary_result.output
    assert "savings" in summary_result.output
    assert "INR 24050.25" in summary_result.output
    assert "2025-12-31" in summary_result.output
    assert "icici-bank_5148_2025-01-01_2025-12-31.xls" in summary_result.output
    assert "166601075148" not in summary_result.output
    assert "...5148" in summary_result.output


def test_account_summary_shows_missing_balance_as_dash(tmp_path) -> None:
    runner = CliRunner()
    runner.invoke(
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
        ],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    result = runner.invoke(
        main,
        ["account", "summary"],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "Bank of America" in result.output
    assert "...6789" in result.output
    assert " - | -" in result.output


def test_account_show_outputs_account_detail_without_full_number(tmp_path) -> None:
    runner = CliRunner()
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "ICICI Bank",
            "--country",
            "IN",
            "--account-number",
            "166601075148",
            "--type",
            "savings",
            "--currency",
            "INR",
            "--display-name",
            "ICICI Joint NRO",
        ],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )
    paths = resolve_app_paths(tmp_path)
    with connect_database(paths) as conn:
        cursor = conn.execute(
            """
            insert into import_files (
                file_name,
                file_hash,
                canonical_file_name
            ) values (?, ?, ?)
            """,
            (
                "ICICI NRO 2025.xls",
                "hash",
                "icici-bank_5148_2025-01-01_2025-12-31.xls",
            ),
        )
        conn.execute(
            """
            update accounts
            set latest_balance_minor_units = ?,
                latest_balance_currency = ?,
                latest_balance_as_of_date = ?,
                latest_balance_source_file_id = ?
            where account_id = 1
            """,
            (2405025, "INR", "2025-12-31", cursor.lastrowid),
        )
        conn.commit()

    result = runner.invoke(
        main,
        ["account", "show", "1"],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "ID: 1" in result.output
    assert "Bank: ICICI Bank" in result.output
    assert "Country: IN" in result.output
    assert "Name: ICICI Joint NRO" in result.output
    assert "Account: ...5148" in result.output
    assert "Latest balance: INR 24050.25" in result.output
    assert "Latest balance as of: 2025-12-31" in result.output
    assert (
        "Latest balance source: icici-bank_5148_2025-01-01_2025-12-31.xls"
        in result.output
    )
    assert "166601075148" not in result.output


def test_account_show_can_reveal_full_account_number_explicitly(tmp_path) -> None:
    runner = CliRunner()
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "ICICI Bank",
            "--country",
            "IN",
            "--account-number",
            "166601075148",
            "--type",
            "savings",
            "--currency",
            "INR",
            "--display-name",
            "ICICI Joint NRO",
        ],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    result = runner.invoke(
        main,
        ["account", "show", "1", "--show-full-account-number"],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "Account: 166601075148" in result.output
    assert "Account: ...5148" not in result.output


def test_account_show_rejects_unknown_account(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["account", "show", "999"],
        env={"BANKBUDDY_HOME": str(tmp_path)},
    )

    assert result.exit_code == 1
    assert "Account not found: 999" in result.output


def test_account_ref_add_list_and_remove(tmp_path) -> None:
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path)}
    add_account_result = runner.invoke(
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
        env=env,
    )

    add_ref_result = runner.invoke(
        main,
        [
            "account",
            "ref",
            "add",
            "--account-id",
            "1",
            "--type",
            "last4",
            "--value",
            "6789",
            "--source-format",
            "boa_pdf",
        ],
        env=env,
    )
    list_result = runner.invoke(main, ["account", "ref", "list"], env=env)
    remove_result = runner.invoke(main, ["account", "ref", "remove", "1"], env=env)
    empty_list_result = runner.invoke(main, ["account", "ref", "list"], env=env)

    assert add_account_result.exit_code == 0
    assert add_ref_result.exit_code == 0
    assert "Added account statement ref 1 for account 1." in add_ref_result.output
    assert list_result.exit_code == 0
    assert "ID | Account | Bank            | Type  | Value | Source" in list_result.output
    assert " 1 |       1 | Bank of America | last4 | 6789  | boa_pdf" in (
        list_result.output
    )
    assert remove_result.exit_code == 0
    assert "Removed account statement ref 1." in remove_result.output
    assert empty_list_result.exit_code == 0
    assert "No account statement refs configured." in empty_list_result.output


def test_account_ref_add_help_includes_examples() -> None:
    result = CliRunner().invoke(main, ["account", "ref", "add", "--help"])

    assert result.exit_code == 0
    assert "Examples:" in result.output
    assert "--type product --value \"Apple Card\" --source-format apple_card_pdf" in (
        result.output
    )
    assert "--type last4 --value 1145 --source-format boa_pdf" in result.output
    assert "--type full_account_number --value <actual-number>" in result.output


def test_account_ref_add_masks_full_account_numbers_in_list(tmp_path) -> None:
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path)}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Example Bank",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )

    add_ref_result = runner.invoke(
        main,
        [
            "account",
            "ref",
            "add",
            "--account-id",
            "1",
            "--type",
            "full_account_number",
            "--value",
            "123456789",
        ],
        env=env,
    )
    list_result = runner.invoke(main, ["account", "ref", "list"], env=env)

    assert add_ref_result.exit_code == 0
    assert list_result.exit_code == 0
    assert "...6789" in list_result.output
    assert "123456789" not in list_result.output


def test_account_ref_add_rejects_ambiguous_ref_for_same_bank_currency(
    tmp_path,
) -> None:
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path)}
    for account_number in ("1111", "2222"):
        runner.invoke(
            main,
            [
                "account",
                "add",
                "--bank",
                "Apple Card",
                "--country",
                "US",
                "--account-number",
                account_number,
                "--type",
                "credit_card",
                "--currency",
                "USD",
            ],
            env=env,
        )
    first = runner.invoke(
        main,
        [
            "account",
            "ref",
            "add",
            "--account-id",
            "1",
            "--type",
            "product",
            "--value",
            "apple-card",
            "--source-format",
            "apple_card_pdf",
        ],
        env=env,
    )
    second = runner.invoke(
        main,
        [
            "account",
            "ref",
            "add",
            "--account-id",
            "2",
            "--type",
            "product",
            "--value",
            "apple-card",
            "--source-format",
            "apple_card_pdf",
        ],
        env=env,
    )

    assert first.exit_code == 0
    assert second.exit_code == 1
    assert "would be ambiguous" in second.output
