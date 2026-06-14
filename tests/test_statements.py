import pytest

from bankbuddy.accounts import Account
from bankbuddy.accounts import add_account
from bankbuddy.database import connect_database
from bankbuddy.paths import AppPaths
from bankbuddy.paths import resolve_app_paths
from bankbuddy.statements import list_statement_files
from bankbuddy.statements import statement_summary
from bankbuddy.statements import StatementFilterError


def add_boa_account(
    paths: AppPaths,
    *,
    account_number: str = "123456789",
    display_name: str | None = "Everyday Checking",
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


def add_statement(
    paths: AppPaths,
    account: Account,
    *,
    start_date: str,
    end_date: str,
    rows_imported: int = 1,
    rows_skipped_duplicate: int = 0,
    file_name: str | None = None,
) -> None:
    canonical_file_name = file_name or (
        f"bank-of-america_6789_{start_date}_{end_date}.pdf"
    )
    with connect_database(paths) as conn:
        bank_id = conn.execute(
            "select bank_id from accounts where account_id = ?",
            (account.account_id,),
        ).fetchone()["bank_id"]
        cursor = conn.execute(
            """
            insert into import_files (
                file_name,
                file_hash,
                bank_id,
                original_file_name,
                canonical_file_name,
                processed_path,
                statement_start_date,
                statement_end_date,
                account_ref,
                source_format
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_file_name,
                f"hash-{account.account_id}-{canonical_file_name}",
                bank_id,
                canonical_file_name,
                canonical_file_name,
                f"processed/bank-of-america/{end_date[:4]}/{end_date[5:7]}/"
                f"{canonical_file_name}",
                start_date,
                end_date,
                "6789",
                "boa_pdf",
            ),
        )
        conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                account_id,
                import_status,
                finished_at,
                rows_parsed,
                rows_imported,
                rows_skipped_duplicate
            ) values (?, ?, ?, ?, current_timestamp, ?, ?, ?)
            """,
            (
                cursor.lastrowid,
                bank_id,
                account.account_id,
                "success",
                rows_imported + rows_skipped_duplicate,
                rows_imported,
                rows_skipped_duplicate,
            ),
        )
        conn.commit()


def test_statement_summary_groups_successful_files_by_year(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    add_statement(
        paths,
        account,
        start_date="2025-01-01",
        end_date="2025-01-31",
        rows_imported=10,
    )
    add_statement(
        paths,
        account,
        start_date="2025-02-01",
        end_date="2025-02-28",
        rows_imported=20,
        rows_skipped_duplicate=2,
    )
    add_statement(
        paths,
        account,
        start_date="2024-12-01",
        end_date="2024-12-31",
        rows_imported=5,
    )

    rows = statement_summary(paths, group_by="year", years=[2025])

    assert len(rows) == 1
    assert rows[0].bank_name == "Bank of America"
    assert rows[0].account_display == "Everyday Checking"
    assert rows[0].year == 2025
    assert rows[0].month is None
    assert rows[0].file_count == 2
    assert rows[0].period_start == "2025-01-01"
    assert rows[0].period_end == "2025-02-28"
    assert rows[0].rows_imported == 30
    assert rows[0].rows_skipped_duplicate == 2


def test_statement_summary_groups_successful_files_by_month(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    add_statement(
        paths,
        account,
        start_date="2025-01-01",
        end_date="2025-01-31",
        rows_imported=10,
    )
    add_statement(
        paths,
        account,
        start_date="2025-02-01",
        end_date="2025-02-28",
        rows_imported=20,
    )

    rows = statement_summary(paths, group_by="month", years=[2025])

    assert [(row.year, row.month, row.file_count) for row in rows] == [
        (2025, 1, 1),
        (2025, 2, 1),
    ]


def test_list_statement_files_orders_by_period(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    add_statement(
        paths,
        account,
        start_date="2025-02-01",
        end_date="2025-02-28",
        rows_imported=20,
    )
    add_statement(
        paths,
        account,
        start_date="2025-01-01",
        end_date="2025-01-31",
        rows_imported=10,
        rows_skipped_duplicate=1,
    )

    rows = list_statement_files(paths, year=2025)

    assert [row.period for row in rows] == [
        "2025-01-01 to 2025-01-31",
        "2025-02-01 to 2025-02-28",
    ]
    assert rows[0].file_name == "bank-of-america_6789_2025-01-01_2025-01-31.pdf"
    assert rows[0].rows_imported == 10
    assert rows[0].rows_skipped_duplicate == 1


def test_statement_summary_resolves_account_last4(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    first_account = add_boa_account(paths, display_name="Checking")
    second_account = add_boa_account(
        paths,
        account_number="555550001",
        display_name="Savings",
    )
    add_statement(
        paths,
        first_account,
        start_date="2025-01-01",
        end_date="2025-01-31",
    )
    add_statement(
        paths,
        second_account,
        start_date="2025-02-01",
        end_date="2025-02-28",
    )

    rows = statement_summary(paths, group_by="year", account_last4="0001")

    assert len(rows) == 1
    assert rows[0].account_display == "Savings"


def test_statement_summary_rejects_ambiguous_account_last4(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    add_boa_account(paths)
    add_boa_account(paths, account_number="555556789", display_name="Other")

    with pytest.raises(StatementFilterError) as exc_info:
        statement_summary(paths, group_by="year", account_last4="6789")

    assert "Account last four digits are ambiguous: 6789." in str(exc_info.value)
