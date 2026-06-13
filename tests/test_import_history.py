from pathlib import Path

from bankbuddy.accounts import Account
from bankbuddy.accounts import add_account
from bankbuddy.database import connect_database
from bankbuddy.import_history import list_import_history
from bankbuddy.imports import import_boa_csv
from bankbuddy.paths import AppPaths
from bankbuddy.paths import resolve_app_paths


BOA_CSV = """Date,Description,Amount,Running Bal.
06/10/2026,COFFEE SHOP,-4.25,100.00
06/11/2026,PAYROLL,2500.00,2600.00
"""


def write_csv(tmp_path: Path, name: str, content: str = BOA_CSV) -> Path:
    csv_path = tmp_path / name
    csv_path.write_text(content, encoding="utf-8")
    return csv_path


def add_boa_account(paths: AppPaths) -> Account:
    return add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="123456789",
        account_type="checking",
        currency="USD",
    )


def test_list_import_history_orders_newest_first(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    csv_path = write_csv(tmp_path, "boa.csv")
    import_boa_csv(paths, csv_path, account_id=account.account_id)
    import_boa_csv(paths, csv_path, account_id=account.account_id)

    rows = list_import_history(paths)

    assert [row.attempt_id for row in rows] == [2, 1]
    assert rows[0].file_name == "boa.csv"
    assert rows[0].canonical_file_name == (
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )
    assert rows[0].processed_path == (
        "processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )
    assert rows[0].bank_name == "Bank of America"
    assert rows[0].account_id == account.account_id
    assert rows[0].status == "success"
    assert rows[0].finished_at is not None
    assert rows[0].rows_parsed == 2
    assert rows[0].rows_imported == 0
    assert rows[0].rows_skipped_duplicate == 2
    assert rows[0].error_message is None


def test_list_import_history_reports_duplicate_path(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    csv_path = write_csv(tmp_path, "boa.csv")
    import_boa_csv(paths, csv_path, account_id=account.account_id)

    with connect_database(paths) as conn:
        file_row = conn.execute(
            """
            select
                import_files.file_id,
                import_files.bank_id,
                import_files.processed_path
            from import_files
            """
        ).fetchone()
        conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                account_id,
                import_status,
                finished_at,
                duplicate_path
            ) values (?, ?, ?, ?, current_timestamp, ?)
            """,
            (
                file_row["file_id"],
                file_row["bank_id"],
                account.account_id,
                "duplicate",
                "duplicates/bank-of-america/2026/06/"
                "bank-of-america_6789_2026-06-10_2026-06-11.csv",
            ),
        )
        conn.commit()

    rows = list_import_history(paths, status="duplicate", limit=1)

    assert len(rows) == 1
    assert rows[0].status == "duplicate"
    assert rows[0].processed_path == file_row["processed_path"]
    assert rows[0].duplicate_path == (
        "duplicates/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )


def test_list_import_history_filters_by_status_and_limit(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    csv_path = write_csv(tmp_path, "boa.csv")
    import_boa_csv(paths, csv_path, account_id=account.account_id)
    with connect_database(paths) as conn:
        file_row = conn.execute("select file_id, bank_id from import_files").fetchone()
        conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                import_status,
                finished_at,
                rows_parsed,
                rows_imported,
                rows_skipped_duplicate,
                error_message
            ) values (?, ?, ?, current_timestamp, ?, ?, ?, ?)
            """,
            (
                file_row["file_id"],
                file_row["bank_id"],
                "failed",
                0,
                0,
                0,
                "Synthetic failure",
            ),
        )
        conn.commit()

    rows = list_import_history(paths, status="failed", limit=1)

    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].account_id is None
    assert rows[0].error_message == "Synthetic failure"
