from pathlib import Path

import pytest

from bankbuddy.accounts import add_account
from bankbuddy.database import connect_database
from bankbuddy.imports import ImportFailure
from bankbuddy.imports import import_boa_csv
from bankbuddy.imports import parse_boa_csv
from bankbuddy.paths import resolve_app_paths


BOA_CSV = """Date,Description,Amount,Running Bal.
06/10/2026,COFFEE SHOP,-4.25,100.00
06/11/2026,PAYROLL,2500.00,2600.00
"""


def write_boa_csv(tmp_path: Path, content: str = BOA_CSV) -> Path:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(content, encoding="utf-8")
    return csv_path


def test_parse_boa_csv_normalizes_rows(tmp_path) -> None:
    csv_path = write_boa_csv(tmp_path)

    rows = parse_boa_csv(csv_path)

    assert len(rows) == 2
    assert rows[0].transaction_date == "2026-06-10"
    assert rows[0].description == "COFFEE SHOP"
    assert rows[0].normalized_description == "coffee shop"
    assert rows[0].amount_minor_units == -425
    assert rows[1].amount_minor_units == 250000


def test_import_boa_csv_inserts_transactions_and_attempt(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="123456789",
        account_type="checking",
        currency="USD",
    )
    csv_path = write_boa_csv(tmp_path)

    summary = import_boa_csv(paths, csv_path, account_id=account.account_id)

    assert summary.rows_parsed == 2
    assert summary.rows_imported == 2
    assert summary.rows_skipped_duplicate == 0

    with connect_database(paths) as conn:
        transactions = conn.execute(
            """
            select
                transaction_date,
                amount_minor_units,
                currency,
                description,
                normalized_description,
                category_name,
                transfer_status
            from transactions
            join categories using (category_id)
            order by transaction_date
            """
        ).fetchall()
        attempt = conn.execute(
            """
            select import_status, rows_parsed, rows_imported, rows_skipped_duplicate
            from import_attempts
            """
        ).fetchone()
        file_row = conn.execute(
            "select file_name, last_success_at from import_files"
        ).fetchone()

    assert [dict(row) for row in transactions] == [
        {
            "transaction_date": "2026-06-10",
            "amount_minor_units": -425,
            "currency": "USD",
            "description": "COFFEE SHOP",
            "normalized_description": "coffee shop",
            "category_name": "Uncategorized",
            "transfer_status": "none",
        },
        {
            "transaction_date": "2026-06-11",
            "amount_minor_units": 250000,
            "currency": "USD",
            "description": "PAYROLL",
            "normalized_description": "payroll",
            "category_name": "Uncategorized",
            "transfer_status": "none",
        },
    ]
    assert dict(attempt) == {
        "import_status": "success",
        "rows_parsed": 2,
        "rows_imported": 2,
        "rows_skipped_duplicate": 0,
    }
    assert file_row["file_name"] == "boa.csv"
    assert file_row["last_success_at"] is not None


def test_import_boa_csv_skips_duplicate_transactions(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="123456789",
        account_type="checking",
        currency="USD",
    )
    csv_path = write_boa_csv(tmp_path)

    first = import_boa_csv(paths, csv_path, account_id=account.account_id)
    second = import_boa_csv(paths, csv_path, account_id=account.account_id)

    with connect_database(paths) as conn:
        transaction_count = conn.execute("select count(*) from transactions").fetchone()[0]

    assert first.rows_imported == 2
    assert second.rows_imported == 0
    assert second.rows_skipped_duplicate == 2
    assert transaction_count == 2


def test_import_boa_csv_requires_bank_of_america_usd_account(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_account(
        paths,
        bank_name="HDFC Bank",
        country="India",
        account_number="123456789",
        account_type="savings",
        currency="INR",
    )
    csv_path = write_boa_csv(tmp_path)

    with pytest.raises(ImportFailure, match="Bank of America USD account"):
        import_boa_csv(paths, csv_path, account_id=account.account_id)
