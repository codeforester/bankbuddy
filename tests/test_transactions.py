from pathlib import Path

import pytest

from bankbuddy.accounts import add_account
from bankbuddy.accounts import Account
from bankbuddy.imports import import_boa_csv
from bankbuddy.paths import AppPaths
from bankbuddy.paths import resolve_app_paths
from bankbuddy.transactions import list_transactions
from bankbuddy.transactions import summarize_transactions
from bankbuddy.transactions import TransactionFilterError
from bankbuddy.transactions import TransactionRow
from bankbuddy.transactions import TransactionSortError


BOA_CSV = """Date,Description,Amount,Running Bal.
06/10/2026,COFFEE SHOP,-4.25,100.00
06/11/2026,PAYROLL,2500.00,2600.00
"""

SECOND_BOA_CSV = """Date,Description,Amount,Running Bal.
06/09/2026,GROCERY STORE,-42.17,100.00
"""


def write_csv(tmp_path: Path, name: str, content: str) -> Path:
    csv_path = tmp_path / name
    csv_path.write_text(content, encoding="utf-8")
    return csv_path


def add_boa_account(
    paths: AppPaths,
    *,
    account_number: str,
    display_name: str | None = None,
) -> Account:
    return add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number=account_number,
        account_type="checking",
        currency="USD",
        display_name=display_name,
    )


def test_list_transactions_orders_by_date_and_id(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(
        paths,
        account_number="123456789",
        display_name="Everyday Checking",
    )
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    rows = list_transactions(paths)

    assert [(row.transaction_date, row.description) for row in rows] == [
        ("2026-06-10", "COFFEE SHOP"),
        ("2026-06-11", "PAYROLL"),
    ]
    assert rows[0].account_display == "Everyday Checking"
    assert rows[0].amount_minor_units == -425
    assert rows[0].currency == "USD"


def test_list_transactions_filters_by_account_and_date_range(tmp_path) -> None:
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

    rows = list_transactions(
        paths,
        account_id=first_account.account_id,
        date_from="2026-06-11",
        date_to="2026-06-11",
    )

    assert len(rows) == 1
    assert rows[0].description == "PAYROLL"
    assert rows[0].account_id == first_account.account_id


def test_list_transactions_filters_debits_and_credits(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    debit_rows = list_transactions(paths, direction="debit")
    credit_rows = list_transactions(paths, direction="credit")

    assert [row.description for row in debit_rows] == ["COFFEE SHOP"]
    assert debit_rows[0].amount_minor_units == -425
    assert [row.description for row in credit_rows] == ["PAYROLL"]
    assert credit_rows[0].amount_minor_units == 250000


def test_list_transactions_direction_composes_with_account_and_dates(tmp_path) -> None:
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

    rows = list_transactions(
        paths,
        account_id=first_account.account_id,
        date_from="2026-06-10",
        date_to="2026-06-10",
        direction="debit",
    )

    assert len(rows) == 1
    assert rows[0].description == "COFFEE SHOP"
    assert rows[0].account_id == first_account.account_id


def test_list_transactions_filters_by_bank_name(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    matching_rows = list_transactions(paths, bank_name="bank of america")
    missing_rows = list_transactions(paths, bank_name="Other Bank")

    assert [row.description for row in matching_rows] == [
        "COFFEE SHOP",
        "PAYROLL",
    ]
    assert missing_rows == []


def test_list_transactions_filters_by_currency(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    matching_rows = list_transactions(paths, currency="usd")
    missing_rows = list_transactions(paths, currency="INR")

    assert [row.description for row in matching_rows] == [
        "COFFEE SHOP",
        "PAYROLL",
    ]
    assert missing_rows == []


def test_list_transactions_filters_by_normalized_account_number(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123 456 789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    matching_rows = list_transactions(paths, account_number="123-456-789")
    missing_rows = list_transactions(paths, account_number="0000")

    assert [row.description for row in matching_rows] == [
        "COFFEE SHOP",
        "PAYROLL",
    ]
    assert missing_rows == []


def test_list_transactions_filters_by_unambiguous_account_last4(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123 456 789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    rows = list_transactions(paths, account_last4="6789")

    assert [row.description for row in rows] == ["COFFEE SHOP", "PAYROLL"]


def test_list_transactions_rejects_invalid_account_last4(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    add_boa_account(paths, account_number="123456789")

    with pytest.raises(
        TransactionFilterError,
        match="Account last four digits must contain exactly four digits",
    ):
        list_transactions(paths, account_last4="789")


def test_list_transactions_rejects_missing_account_last4(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    add_boa_account(paths, account_number="123456789")

    with pytest.raises(TransactionFilterError, match="No account matches"):
        list_transactions(paths, account_last4="0000")


def test_list_transactions_rejects_ambiguous_account_last4(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    add_boa_account(paths, account_number="123456789")
    add_boa_account(paths, account_number="987656789")

    with pytest.raises(
        TransactionFilterError,
        match="Account last four digits are ambiguous",
    ):
        list_transactions(paths, account_last4="6789")


def test_list_transactions_sorts_by_field_directions(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    rows = list_transactions(paths, sort="amount:desc,date")

    assert [row.description for row in rows] == ["PAYROLL", "COFFEE SHOP"]


def test_list_transactions_applies_default_sort_order(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    rows = list_transactions(paths, sort="date", default_order="desc")

    assert [row.description for row in rows] == ["PAYROLL", "COFFEE SHOP"]


def test_list_transactions_rejects_unknown_sort_fields(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    with pytest.raises(TransactionSortError, match="Unsupported sort field"):
        list_transactions(paths, sort="posted_at")


def test_list_transactions_rejects_unknown_sort_directions(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    with pytest.raises(TransactionSortError, match="Unsupported sort direction"):
        list_transactions(paths, sort="amount:newest")


def test_summarize_transactions_groups_by_currency() -> None:
    rows = [
        TransactionRow(1, 1, "2026-06-10", "Checking", -425, "USD", "COFFEE"),
        TransactionRow(2, 1, "2026-06-11", "Checking", 250000, "USD", "PAYROLL"),
        TransactionRow(3, 2, "2026-06-12", "Savings", -999, "INR", "TEA"),
    ]

    summaries = summarize_transactions(rows)

    assert [
        (
            row.currency,
            row.transaction_count,
            row.debit_minor_units,
            row.credit_minor_units,
            row.net_minor_units,
        )
        for row in summaries
    ] == [
        ("INR", 1, -999, 0, -999),
        ("USD", 2, -425, 250000, 249575),
    ]


def test_summarize_transactions_respects_filtered_rows(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    summaries = summarize_transactions(list_transactions(paths, direction="debit"))

    assert len(summaries) == 1
    assert summaries[0].currency == "USD"
    assert summaries[0].transaction_count == 1
    assert summaries[0].debit_minor_units == -425
    assert summaries[0].credit_minor_units == 0
    assert summaries[0].net_minor_units == -425


def test_list_transactions_uses_masked_account_when_display_name_is_missing(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "boa.csv", BOA_CSV),
        account_id=account.account_id,
    )

    rows = list_transactions(paths)

    assert rows[0].account_display == "...6789"
