from click.testing import CliRunner

from bankbuddy.accounts import Account
from bankbuddy.accounts import add_account
from bankbuddy.cli import main
from bankbuddy.database import connect_database
from bankbuddy.paths import AppPaths
from bankbuddy.paths import resolve_app_paths


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
                f"hash-{account.account_id}-{canonical_file_name}",
                bank_id,
                canonical_file_name,
                canonical_file_name,
                f"processed/bank-of-america/2025/01/{canonical_file_name}",
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
                rows_imported
            ) values (?, ?, ?, ?, current_timestamp, ?, ?)
            """,
            (cursor.lastrowid, bank_id, account.account_id, "success", 1, 1),
        )
        conn.commit()


def seed_home(tmp_path):
    home = tmp_path / "home"
    paths = resolve_app_paths(home)
    account = add_boa_account(paths)
    add_statement(
        paths,
        account,
        start_date="2025-01-10",
        end_date="2025-01-20",
    )
    return home, paths, account


def test_audit_statements_outputs_year_window(tmp_path) -> None:
    home, _paths, _account = seed_home(tmp_path)

    result = CliRunner().invoke(
        main,
        ["audit", "statements", "--years", "2025"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Account" in result.output
    assert "Bank" in result.output
    assert "Window" in result.output
    assert "Everyday Checking" in result.output
    assert "Bank of America" in result.output
    assert "2025-01-01 to 2025-12-31" in result.output
    assert "missing" in result.output
    assert "2025-01-01 to 2025-01-09" in result.output
    assert "covered" in result.output
    assert "2025-01-10 to 2025-01-20" in result.output


def test_audit_statements_outputs_explicit_date_window(tmp_path) -> None:
    home, _paths, _account = seed_home(tmp_path)

    result = CliRunner().invoke(
        main,
        [
            "audit",
            "statements",
            "--from",
            "2025-01-01",
            "--to",
            "2025-01-31",
        ],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "2025-01-01 to 2025-01-31" in result.output
    assert "2025-01-21 to 2025-01-31" in result.output


def test_audit_statements_filters_by_account_last4(tmp_path) -> None:
    home, paths, _first_account = seed_home(tmp_path)
    second_account = add_boa_account(
        paths,
        account_number="555550001",
        display_name="Savings",
    )
    add_statement(
        paths,
        second_account,
        start_date="2025-02-01",
        end_date="2025-02-28",
    )

    result = CliRunner().invoke(
        main,
        ["audit", "statements", "--account-last4", "0001", "--years", "2025"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Savings" in result.output
    assert "Everyday Checking" not in result.output


def test_audit_statements_rejects_conflicting_date_selectors(tmp_path) -> None:
    home, _paths, _account = seed_home(tmp_path)

    result = CliRunner().invoke(
        main,
        [
            "audit",
            "statements",
            "--years",
            "2025",
            "--from",
            "2025-01-01",
            "--to",
            "2025-12-31",
        ],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "--years cannot be combined with --from or --to" in result.output


def test_audit_statements_requires_complete_date_range(tmp_path) -> None:
    home, _paths, _account = seed_home(tmp_path)

    result = CliRunner().invoke(
        main,
        ["audit", "statements", "--from", "2025-01-01"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "--from and --to must be provided together" in result.output


def test_audit_statements_rejects_bad_years(tmp_path) -> None:
    home, _paths, _account = seed_home(tmp_path)

    result = CliRunner().invoke(
        main,
        ["audit", "statements", "--years", "2025,25"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "Years must be four-digit values" in result.output
