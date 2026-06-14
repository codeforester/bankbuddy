from click.testing import CliRunner

from bankbuddy.accounts import Account
from bankbuddy.accounts import add_account
from bankbuddy.cli import main
from bankbuddy.database import connect_database
from bankbuddy.paths import AppPaths
from bankbuddy.paths import resolve_app_paths


def add_boa_account(paths: AppPaths) -> Account:
    return add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="123456789",
        account_type="checking",
        currency="USD",
        display_name="Everyday Checking",
    )


def add_statement(
    paths: AppPaths,
    account: Account,
    *,
    start_date: str,
    end_date: str,
    rows_imported: int = 1,
    rows_skipped_duplicate: int = 0,
) -> None:
    canonical_file_name = (
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
                f"hash-{canonical_file_name}",
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


def seed_home(tmp_path):
    home = tmp_path / "home"
    paths = resolve_app_paths(home)
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
    return home, account


def test_statements_summary_outputs_year_inventory(tmp_path) -> None:
    home, _account = seed_home(tmp_path)

    result = CliRunner().invoke(
        main,
        ["statements", "summary", "--years", "2025"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Bank" in result.output
    assert "Account" in result.output
    assert "Bank of America" in result.output
    assert "Everyday Checking" in result.output
    assert "2025" in result.output
    assert "2025-01-01" in result.output
    assert "2025-02-28" in result.output
    assert "30" in result.output
    assert "2" in result.output
    assert "2024-12-31" not in result.output


def test_statements_summary_outputs_month_inventory(tmp_path) -> None:
    home, _account = seed_home(tmp_path)

    result = CliRunner().invoke(
        main,
        ["statements", "summary", "--by", "month", "--years", "2025"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Month" in result.output
    assert "01" in result.output
    assert "02" in result.output
    assert "2025-01-31" in result.output
    assert "2025-02-28" in result.output


def test_statements_list_outputs_statement_files_for_year(tmp_path) -> None:
    home, _account = seed_home(tmp_path)

    result = CliRunner().invoke(
        main,
        ["statements", "list", "--year", "2025"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Bank" in result.output
    assert "Account" in result.output
    assert "2025-01-01 to 2025-01-31" in result.output
    assert "bank-of-america_6789_2025-01-01_2025-01-31.pdf" in result.output
    assert "2025-02-01 to 2025-02-28" in result.output
    assert "bank-of-america_6789_2025-02-01_2025-02-28.pdf" in result.output
    assert "2024-12-31" not in result.output


def test_statements_summary_rejects_invalid_grouping(tmp_path) -> None:
    home, _account = seed_home(tmp_path)

    result = CliRunner().invoke(
        main,
        ["statements", "summary", "--by", "week"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "Invalid value for '--by'" in result.output
