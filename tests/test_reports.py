from pathlib import Path

from bankbuddy.accounts import Account
from bankbuddy.accounts import add_account
from bankbuddy.database import connect_database
from bankbuddy.imports import import_boa_csv
from bankbuddy.paths import AppPaths
from bankbuddy.paths import resolve_app_paths
from bankbuddy.reports import spending_report


BOA_CSV = """Date,Description,Amount,Running Bal.
05/19/2026,GROCERY STORE,-42.17,100.00
06/10/2026,COFFEE SHOP,-4.25,95.75
06/11/2026,PAYROLL,2500.00,2595.75
"""

SECOND_BOA_CSV = """Date,Description,Amount,Running Bal.
06/12/2026,BOOK STORE,-19.99,100.00
"""


def write_csv(tmp_path: Path, name: str, content: str) -> Path:
    csv_path = tmp_path / name
    csv_path.write_text(content, encoding="utf-8")
    return csv_path


def add_boa_account(paths: AppPaths, *, account_number: str) -> Account:
    return add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number=account_number,
        account_type="checking",
        currency="USD",
    )


def test_spending_report_groups_outgoing_transactions_by_currency_and_category(
    tmp_path,
) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    first_account = add_boa_account(paths, account_number="123456789")
    second_account = add_boa_account(paths, account_number="987654321")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "first.csv", BOA_CSV),
        account_id=first_account.account_id,
    )
    import_boa_csv(
        paths,
        write_csv(tmp_path, "second.csv", SECOND_BOA_CSV),
        account_id=second_account.account_id,
    )

    rows = spending_report(paths, year=2026)

    assert [row.currency for row in rows] == ["USD"]
    assert rows[0].category_name == "Uncategorized"
    assert rows[0].transaction_count == 3
    assert rows[0].spending_minor_units == 6641


def test_spending_report_filters_to_month(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    rows = spending_report(paths, year=2026, month=6)

    assert len(rows) == 1
    assert rows[0].transaction_count == 1
    assert rows[0].spending_minor_units == 425


def test_spending_report_excludes_confirmed_transfers(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )
    with connect_database(paths) as conn:
        conn.execute(
            "update transactions set transfer_status = 'confirmed' where description = ?",
            ("COFFEE SHOP",),
        )
        conn.commit()

    rows = spending_report(paths, year=2026, month=6)

    assert rows == []
