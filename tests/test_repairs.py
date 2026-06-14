from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from click.testing import CliRunner

from bankbuddy.accounts import add_account
from bankbuddy.cli import main
from bankbuddy.database import connect_database
from bankbuddy.repairs import repair_boa_pdf_imports
from bankbuddy.paths import resolve_app_paths


BOA_PDF_TEXT = """
Bank of America
Account number 1234 5678 901145
Statement Period: January 1, 2026 through January 31, 2026
Transaction activity
Date Description Amount
01/20/26 Isha Foundation DES:DEBITS ID:Rpadmanabhaiah INDN:Ramesh Padmanabhaiah CO -100.00
ID:111111111 PPD
01/20/26 Isha Foundation DES:DEBITS ID:Rpadmanabhaiah INDN:Ramesh Padmanabhaiah CO -100.00
ID:222222222 PPD
"""

LEGACY_DESCRIPTION = (
    "Isha Foundation DES:DEBITS ID:Rpadmanabhaiah INDN:Ramesh Padmanabhaiah CO"
)


def legacy_boa_pdf_hash(
    *,
    transaction_date: str,
    amount_minor_units: int,
    normalized_description: str,
) -> str:
    parts = [
        "boa_pdf",
        transaction_date,
        str(amount_minor_units),
        normalized_description,
        "",
    ]
    return sha256("|".join(parts).encode("utf-8")).hexdigest()


def seed_old_boa_pdf_import(tmp_path: Path) -> tuple[Path, int]:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="12345678901145",
        account_type="checking",
        currency="USD",
        display_name="Everyday Checking",
    )
    processed_path = (
        "processed/bank-of-america/2026/01/"
        "bank-of-america_1145_2026-01-01_2026-01-31.pdf"
    )
    (paths.root / processed_path).parent.mkdir(parents=True, exist_ok=True)
    (paths.root / processed_path).write_bytes(b"%PDF-1.4 placeholder")
    legacy_hash = legacy_boa_pdf_hash(
        transaction_date="2026-01-20",
        amount_minor_units=-10000,
        normalized_description="isha foundation des:debits id:rpadmanabhaiah "
        "indn:ramesh padmanabhaiah co",
    )
    with connect_database(paths) as conn:
        bank_id = conn.execute(
            "select bank_id from banks where bank_name = ?",
            ("Bank of America",),
        ).fetchone()["bank_id"]
        category_id = conn.execute(
            "select category_id from categories where category_name = ?",
            ("Uncategorized",),
        ).fetchone()["category_id"]
        cursor = conn.execute(
            """
            insert into import_files (
                file_name,
                file_hash,
                bank_id,
                original_file_name,
                canonical_file_name,
                source_path,
                processed_path,
                statement_start_date,
                statement_end_date,
                account_ref,
                source_format,
                last_success_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
            """,
            (
                "statement.pdf",
                "file-hash-1",
                bank_id,
                "statement.pdf",
                "bank-of-america_1145_2026-01-01_2026-01-31.pdf",
                "/downloads/statement.pdf",
                processed_path,
                "2026-01-01",
                "2026-01-31",
                "1145",
                "boa_pdf",
            ),
        )
        file_id = int(cursor.lastrowid)
        conn.execute(
            """
            insert into transactions (
                account_id,
                category_id,
                file_id,
                transaction_date,
                amount_minor_units,
                currency,
                description,
                normalized_description,
                source_row_key,
                transaction_hash,
                transfer_status
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account.account_id,
                category_id,
                file_id,
                "2026-01-20",
                -10000,
                "USD",
                LEGACY_DESCRIPTION,
                "isha foundation des:debits id:rpadmanabhaiah "
                "indn:ramesh padmanabhaiah co",
                "7",
                legacy_hash,
                "none",
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
            ) values (?, ?, ?, 'success', current_timestamp, 2, 1, 1)
            """,
            (file_id, bank_id, account.account_id),
        )
        conn.commit()
    return paths.root, account.account_id


def test_repair_boa_pdf_imports_dry_run_plans_without_writes(tmp_path, monkeypatch) -> None:
    home, _account_id = seed_old_boa_pdf_import(tmp_path)
    monkeypatch.setattr("bankbuddy.repairs.extract_pdf_text", lambda _path: BOA_PDF_TEXT)
    paths = resolve_app_paths(home)

    summary = repair_boa_pdf_imports(paths, dry_run=True)

    assert summary.dry_run is True
    assert summary.files_scanned == 1
    assert summary.files_changed == 1
    assert summary.hashes_updated == 1
    assert summary.rows_inserted == 1
    assert summary.attempts_updated == 1
    with connect_database(paths) as conn:
        attempt = conn.execute(
            "select rows_imported, rows_skipped_duplicate from import_attempts"
        ).fetchone()
        transaction_count = conn.execute(
            "select count(*) as count from transactions"
        ).fetchone()["count"]
        description = conn.execute(
            "select description from transactions"
        ).fetchone()["description"]
    assert dict(attempt) == {"rows_imported": 1, "rows_skipped_duplicate": 1}
    assert transaction_count == 1
    assert description == LEGACY_DESCRIPTION


def test_repair_boa_pdf_imports_apply_updates_hashes_and_inserts_missing_rows(
    tmp_path,
    monkeypatch,
) -> None:
    home, _account_id = seed_old_boa_pdf_import(tmp_path)
    monkeypatch.setattr("bankbuddy.repairs.extract_pdf_text", lambda _path: BOA_PDF_TEXT)
    paths = resolve_app_paths(home)

    summary = repair_boa_pdf_imports(paths, dry_run=False)

    assert summary.dry_run is False
    assert summary.files_changed == 1
    assert summary.hashes_updated == 1
    assert summary.rows_inserted == 1
    assert summary.attempts_updated == 1
    with connect_database(paths) as conn:
        transactions = conn.execute(
            """
            select description, source_row_key
            from transactions
            order by source_row_key
            """
        ).fetchall()
        attempt = conn.execute(
            "select rows_parsed, rows_imported, rows_skipped_duplicate from import_attempts"
        ).fetchone()
    assert [dict(row) for row in transactions] == [
        {
            "description": LEGACY_DESCRIPTION + " ID:111111111 PPD",
            "source_row_key": "7",
        },
        {
            "description": LEGACY_DESCRIPTION + " ID:222222222 PPD",
            "source_row_key": "9",
        },
    ]
    assert dict(attempt) == {
        "rows_parsed": 2,
        "rows_imported": 2,
        "rows_skipped_duplicate": 0,
    }


def test_repair_boa_pdf_imports_is_idempotent_after_apply(tmp_path, monkeypatch) -> None:
    home, _account_id = seed_old_boa_pdf_import(tmp_path)
    monkeypatch.setattr("bankbuddy.repairs.extract_pdf_text", lambda _path: BOA_PDF_TEXT)
    paths = resolve_app_paths(home)

    repair_boa_pdf_imports(paths, dry_run=False)
    summary = repair_boa_pdf_imports(paths, dry_run=True)

    assert summary.files_scanned == 1
    assert summary.files_changed == 0
    assert summary.hashes_updated == 0
    assert summary.rows_inserted == 0
    assert summary.attempts_updated == 0


def test_repair_boa_pdf_imports_cli_defaults_to_dry_run(tmp_path, monkeypatch) -> None:
    home, _account_id = seed_old_boa_pdf_import(tmp_path)
    monkeypatch.setattr("bankbuddy.repairs.extract_pdf_text", lambda _path: BOA_PDF_TEXT)
    runner = CliRunner()

    result = runner.invoke(
        main,
        ["repair", "bofa-pdf-imports"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Dry run: yes" in result.output
    assert "Files scanned: 1" in result.output
    assert "Transaction hashes to update: 1" in result.output
    assert "Rows to insert: 1" in result.output
    assert "Import attempts to update: 1" in result.output
    assert "Database changed: no" in result.output
    with connect_database(resolve_app_paths(home)) as conn:
        assert conn.execute("select count(*) from transactions").fetchone()[0] == 1


def test_repair_boa_pdf_imports_cli_apply_repairs_database(tmp_path, monkeypatch) -> None:
    home, _account_id = seed_old_boa_pdf_import(tmp_path)
    monkeypatch.setattr("bankbuddy.repairs.extract_pdf_text", lambda _path: BOA_PDF_TEXT)
    runner = CliRunner()

    result = runner.invoke(
        main,
        ["repair", "bofa-pdf-imports", "--apply"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Dry run: no" in result.output
    assert "Database changed: yes" in result.output
    with connect_database(resolve_app_paths(home)) as conn:
        assert conn.execute("select count(*) from transactions").fetchone()[0] == 2
        attempt = conn.execute(
            "select rows_imported, rows_skipped_duplicate from import_attempts"
        ).fetchone()
    assert dict(attempt) == {"rows_imported": 2, "rows_skipped_duplicate": 0}


def test_repair_boa_pdf_imports_cli_apply_reports_no_change_when_clean(
    tmp_path,
    monkeypatch,
) -> None:
    home, _account_id = seed_old_boa_pdf_import(tmp_path)
    monkeypatch.setattr("bankbuddy.repairs.extract_pdf_text", lambda _path: BOA_PDF_TEXT)
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(home)}

    first = runner.invoke(main, ["repair", "bofa-pdf-imports", "--apply"], env=env)
    second = runner.invoke(main, ["repair", "bofa-pdf-imports", "--apply"], env=env)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Files changed: 0" in second.output
    assert "Database changed: no" in second.output
