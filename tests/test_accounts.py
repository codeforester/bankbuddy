import pytest

from bankbuddy import accounts
from bankbuddy.accounts import add_account
from bankbuddy.accounts import BankAlreadyExistsError
from bankbuddy.accounts import list_accounts
from bankbuddy.accounts import list_banks
from bankbuddy.accounts import masked_account_number
from bankbuddy.accounts import rename_bank
from bankbuddy.accounts import update_account
from bankbuddy.database import connect_database
from bankbuddy.paths import resolve_app_paths


def test_masked_account_number_shows_only_suffix() -> None:
    assert masked_account_number("123456789") == "...6789"
    assert masked_account_number("123") == "...123"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("US", "US"),
        ("usa", "US"),
        ("United States", "US"),
        ("United States of America", "US"),
        ("IN", "IN"),
        ("India", "IN"),
    ],
)
def test_normalize_country_code_accepts_supported_aliases(
    value: str,
    expected: str,
) -> None:
    assert accounts.normalize_country_code(value) == expected


def test_normalize_country_code_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="Unsupported country"):
        accounts.normalize_country_code("Atlantis")


def test_list_account_summaries_includes_latest_balance_source(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)
    account = add_account(
        paths,
        bank_name="ICICI Bank",
        country="IN",
        account_number="166601075148",
        account_type="savings",
        currency="INR",
        display_name="ICICI Joint NRO",
    )
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
            where account_id = ?
            """,
            (
                2405025,
                "INR",
                "2025-12-31",
                cursor.lastrowid,
                account.account_id,
            ),
        )
        conn.commit()

    summaries = accounts.list_account_summaries(paths)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.account_id == account.account_id
    assert summary.bank_name == "ICICI Bank"
    assert summary.display_name == "ICICI Joint NRO"
    assert summary.latest_balance_minor_units == 2405025
    assert summary.latest_balance_currency == "INR"
    assert summary.latest_balance_as_of_date == "2025-12-31"
    assert summary.latest_balance_source_file_id == cursor.lastrowid
    assert (
        summary.latest_balance_source
        == "icici-bank_5148_2025-01-01_2025-12-31.xls"
    )


def test_get_account_summary_returns_none_for_missing_account(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    assert accounts.get_account_summary(paths, account_id=999) is None


def test_list_banks_returns_configured_banks(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)
    add_account(
        paths,
        bank_name="ICICI Bank",
        country="IN",
        account_number="166601075148",
        account_type="savings",
        currency="INR",
    )
    add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="123456789",
        account_type="checking",
        currency="USD",
    )

    banks = list_banks(paths)

    assert [
        (bank.bank_name, bank.country, bank.default_currency)
        for bank in banks
    ] == [
        ("Bank of America", "US", "USD"),
        ("ICICI Bank", "IN", "INR"),
    ]


def test_rename_bank_updates_existing_accounts(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)
    add_account(
        paths,
        bank_name="Apple GS",
        country="US",
        account_number="111122220932",
        account_type="credit_card",
        currency="USD",
    )
    bank = list_banks(paths)[0]

    renamed = rename_bank(paths, bank_id=bank.bank_id, bank_name="Apple Card")

    assert renamed.bank_name == "Apple Card"
    assert renamed.country == "US"
    assert list_accounts(paths)[0].bank_name == "Apple Card"


def test_rename_bank_rejects_duplicate_bank_name(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)
    add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="123456789",
        account_type="checking",
        currency="USD",
    )
    add_account(
        paths,
        bank_name="Apple GS",
        country="US",
        account_number="111122220932",
        account_type="credit_card",
        currency="USD",
    )
    apple_bank = [
        bank for bank in list_banks(paths) if bank.bank_name == "Apple GS"
    ][0]

    with pytest.raises(BankAlreadyExistsError, match="Bank already exists"):
        rename_bank(
            paths,
            bank_id=apple_bank.bank_id,
            bank_name="Bank of America",
        )


def test_update_account_display_name(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)
    account = add_account(
        paths,
        bank_name="Apple Card",
        country="US",
        account_number="111122220932",
        account_type="credit_card",
        currency="USD",
        display_name="Old Name",
    )

    updated = update_account(
        paths,
        account_id=account.account_id,
        display_name="Apple Card",
    )

    assert updated.display_name == "Apple Card"
    assert list_accounts(paths)[0].display_name == "Apple Card"


def test_update_account_display_name_can_clear_value(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)
    account = add_account(
        paths,
        bank_name="Apple Card",
        country="US",
        account_number="111122220932",
        account_type="credit_card",
        currency="USD",
        display_name="Old Name",
    )

    updated = update_account(
        paths,
        account_id=account.account_id,
        display_name="",
    )

    assert updated.display_name is None
