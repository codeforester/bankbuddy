from click.testing import CliRunner

from bankbuddy.accounts import add_account
from bankbuddy.cli import main
from bankbuddy.imports import import_boa_csv
from bankbuddy.paths import resolve_app_paths


BOA_CSV = """Date,Description,Amount,Running Bal.
05/19/2026,GROCERY STORE,-42.17,100.00
06/10/2026,COFFEE SHOP,-4.25,95.75
06/11/2026,PAYROLL,2500.00,2595.75
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
    )
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    import_boa_csv(paths, csv_path, account_id=account.account_id)
    return home


def test_report_spending_outputs_yearly_summary(tmp_path) -> None:
    home = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["report", "spending", "--year", "2026"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Category  Currency  Transactions  Spending" in result.output
    assert "Uncategorized  USD  2  46.42" in result.output


def test_report_spending_outputs_monthly_summary(tmp_path) -> None:
    home = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["report", "spending", "--year", "2026", "--month", "6"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Uncategorized  USD  1  4.25" in result.output
    assert "46.42" not in result.output


def test_report_spending_reports_empty_state(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["report", "spending", "--year", "2026"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "No spending found for 2026." in result.output
