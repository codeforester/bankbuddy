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
    assert "ID | Date       | Account" in result.output
    assert "---+" in result.output
    assert "ID  Date" not in result.output
    assert " 1 | 2026-06-10 | Everyday Checking |   -4.25 | USD" in (
        result.output
    )
    assert " 2 | 2026-06-11 | Everyday Checking | 2500.00 | USD" in (
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


def test_tx_list_filters_by_bank_name(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--bank", "bank of america"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" in result.output


def test_tx_list_filters_by_currency(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--currency", "usd"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" in result.output


def test_tx_list_filters_by_account_number(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--account-number", "123 456 789"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" in result.output
    assert "123456789" not in result.output


def test_tx_list_filters_by_account_last4(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--account-last4", "6789"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "COFFEE SHOP" in result.output
    assert "PAYROLL" in result.output


def test_tx_list_rejects_missing_account_last4(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--account-last4", "0000"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "No account matches last four digits: 0000." in result.output


def test_tx_list_rejects_ambiguous_account_last4(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)
    paths = resolve_app_paths(home)
    add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="987656789",
        account_type="checking",
        currency="USD",
        display_name="Other Checking",
    )

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--account-last4", "6789"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "Account last four digits are ambiguous: 6789." in result.output


def test_tx_list_sorts_by_amount_descending(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--sort", "amount:desc"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert result.output.index("PAYROLL") < result.output.index("COFFEE SHOP")


def test_tx_list_uses_global_sort_order(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--sort", "date", "--order", "desc"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert result.output.index("PAYROLL") < result.output.index("COFFEE SHOP")


def test_tx_list_rejects_invalid_sort_field(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--sort", "posted_at"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "Unsupported sort field" in result.output


def test_tx_list_outputs_compact_view(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--view", "compact"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Date       |  Amount | Currency | Description" in result.output
    assert "2026-06-10 |   -4.25 | USD" in result.output
    assert "Everyday Checking" not in result.output


def test_tx_list_outputs_ledger_view(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--view", "ledger"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "ID | Date       | Account" in result.output
    assert "Type   |  Amount | Currency | Description" in result.output
    assert " 1 | 2026-06-10 | Everyday Checking | debit" in (
        result.output
    )
    assert " 2 | 2026-06-11 | Everyday Checking | credit | 2500.00" in (
        result.output
    )


def test_tx_list_outputs_summary(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--summary"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Summary" in result.output
    assert "Currency  Transactions  Debits  Credits  Net" in result.output
    assert "USD  2  -4.25  2500.00  2495.75" in result.output


def test_tx_list_summary_respects_direction_filter(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--direction", "debit", "--summary"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "USD  1  -4.25  0.00  -4.25" in result.output
    assert "PAYROLL" not in result.output


def test_tx_list_outputs_csv_format(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--format", "csv"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "id,date,account,amount,currency,description",
        "1,2026-06-10,Everyday Checking,-4.25,USD,COFFEE SHOP",
        "2,2026-06-11,Everyday Checking,2500.00,USD,PAYROLL",
    ]


def test_tx_list_outputs_tsv_format_with_ledger_view(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--view", "ledger", "--format", "tsv"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "id\tdate\taccount\ttype\tamount\tcurrency\tdescription",
        "1\t2026-06-10\tEveryday Checking\tdebit\t-4.25\tUSD\tCOFFEE SHOP",
        "2\t2026-06-11\tEveryday Checking\tcredit\t2500.00\tUSD\tPAYROLL",
    ]


def test_tx_list_rejects_summary_for_csv_format(tmp_path) -> None:
    home, _account = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["tx", "list", "--format", "csv", "--summary"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "--summary is only supported with --format pretty" in result.output


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
