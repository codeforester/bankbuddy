from click.testing import CliRunner

from bankbuddy.accounts import add_account
from bankbuddy.cli import main
from bankbuddy.imports import import_boa_csv
from bankbuddy.paths import resolve_app_paths


BOA_CSV = """Date,Description,Amount,Running Bal.
06/10/2026,COFFEE SHOP,-4.25,100.00
06/11/2026,PAYROLL,2500.00,2600.00
"""


def seed_transactions(tmp_path):
    home = tmp_path / "home"
    paths = resolve_app_paths(home)
    account = add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="123456789",
        account_type="checking",
        currency="USD",
        display_name="Everyday Checking",
    )
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    import_boa_csv(paths, csv_path, account_id=account.account_id)
    return home, account


def test_tx_list_outputs_imported_transactions(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "ID  Date  Account  Amount  Currency  Description" in result.output
    assert "1  2026-06-10  Everyday Checking  -4.25  USD  COFFEE SHOP" in (
        result.output
    )
    assert "2  2026-06-11  Everyday Checking  2500.00  USD  PAYROLL" in (
        result.output
    )
    assert "123456789" not in result.output


def test_tx_list_filters_by_account_id_and_date_range(tmp_path) -> None:
    home, account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        [
            "tx",
            "list",
            "--account-id",
            str(account.account_id),
            "--from",
            "2026-06-11",
            "--to",
            "2026-06-11",
        ],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "PAYROLL" in result.output
    assert "COFFEE SHOP" not in result.output


def test_tx_list_filters_by_debit_direction(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--direction", "debit"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" not in result.output


def test_tx_list_filters_by_credit_direction(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--direction", "credit"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "PAYROLL" in result.output
    assert "COFFEE SHOP" not in result.output


def test_tx_list_reports_empty_state(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["tx", "list"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "No transactions found." in result.output


def test_tx_list_rejects_invalid_dates(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["tx", "list", "--from", "06/11/2026"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "Invalid date" in result.output
