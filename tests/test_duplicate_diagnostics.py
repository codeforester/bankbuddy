from __future__ import annotations

from pathlib import Path

from bankbuddy.accounts import add_account
from bankbuddy.database import connect_database
from bankbuddy.duplicate_diagnostics import list_duplicate_transaction_diagnostics
from bankbuddy.imports import parse_boa_pdf_text
from bankbuddy.imports import transaction_hash
from bankbuddy.paths import resolve_app_paths


BOA_PDF_TEXT = """
Bank of America
Account number 1234 5678 901145
Statement Period: January 1, 2026 through January 31, 2026
Transaction activity
Date Description Amount
01/20/26 COFFEE SHOP -4.25
01/21/26 PAYROLL 2500.00
"""


def seed_duplicate_pdf_attempt(tmp_path: Path) -> tuple[Path, int, int]:
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
    parsed_rows = parse_boa_pdf_text(BOA_PDF_TEXT)
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
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                "2026-06-14 10:00:00",
            ),
        )
        file_id = int(cursor.lastrowid)
        for parsed in parsed_rows:
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
                    transfer_status,
                    created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account.account_id,
                    category_id,
                    file_id,
                    parsed.transaction_date,
                    parsed.amount_minor_units,
                    "USD",
                    parsed.description,
                    parsed.normalized_description,
                    parsed.source_row_key,
                    transaction_hash(parsed, source_format="boa_pdf"),
                    "none",
                    "2026-06-14 10:00:00",
                ),
            )
        conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                account_id,
                import_status,
                started_at,
                finished_at,
                rows_parsed,
                rows_imported,
                rows_skipped_duplicate
            ) values (?, ?, ?, 'success', ?, ?, 2, 2, 0)
            """,
            (
                file_id,
                bank_id,
                account.account_id,
                "2026-06-14 10:00:00",
                "2026-06-14 10:00:01",
            ),
        )
        duplicate_cursor = conn.execute(
            """
            insert into import_attempts (
                file_id,
                bank_id,
                account_id,
                import_status,
                started_at,
                finished_at,
                rows_parsed,
                rows_imported,
                rows_skipped_duplicate
            ) values (?, ?, ?, 'success', ?, ?, 2, 0, 2)
            """,
            (
                file_id,
                bank_id,
                account.account_id,
                "2026-06-14 11:00:00",
                "2026-06-14 11:00:01",
            ),
        )
        duplicate_attempt_id = int(duplicate_cursor.lastrowid)
        conn.commit()
    return paths.root, account.account_id, duplicate_attempt_id


def test_list_duplicate_transaction_diagnostics_reconstructs_skipped_rows(
    tmp_path,
    monkeypatch,
) -> None:
    home, _account_id, duplicate_attempt_id = seed_duplicate_pdf_attempt(tmp_path)
    monkeypatch.setattr(
        "bankbuddy.duplicate_diagnostics.extract_pdf_text",
        lambda _path: BOA_PDF_TEXT,
    )

    rows = list_duplicate_transaction_diagnostics(resolve_app_paths(home))

    assert len(rows) == 2
    assert [row.attempt_id for row in rows] == [
        duplicate_attempt_id,
        duplicate_attempt_id,
    ]
    assert [row.candidate_description for row in rows] == [
        "COFFEE SHOP",
        "PAYROLL",
    ]
    assert [row.matched_description for row in rows] == [
        "COFFEE SHOP",
        "PAYROLL",
    ]
    assert rows[0].bank_name == "Bank of America"
    assert rows[0].account_display == "Everyday Checking"
    assert rows[0].statement_period == "2026-01-01 to 2026-01-31"
    assert rows[0].source_format == "boa_pdf"


def test_list_duplicate_transaction_diagnostics_filters_by_attempt_and_year(
    tmp_path,
    monkeypatch,
) -> None:
    home, _account_id, duplicate_attempt_id = seed_duplicate_pdf_attempt(tmp_path)
    monkeypatch.setattr(
        "bankbuddy.duplicate_diagnostics.extract_pdf_text",
        lambda _path: BOA_PDF_TEXT,
    )
    paths = resolve_app_paths(home)

    rows = list_duplicate_transaction_diagnostics(
        paths,
        attempt_id=duplicate_attempt_id,
        year=2026,
    )
    wrong_year_rows = list_duplicate_transaction_diagnostics(paths, year=2025)

    assert len(rows) == 2
    assert wrong_year_rows == []


def test_list_duplicate_transaction_diagnostics_filters_by_account_last4(
    tmp_path,
    monkeypatch,
) -> None:
    home, _account_id, _duplicate_attempt_id = seed_duplicate_pdf_attempt(tmp_path)
    monkeypatch.setattr(
        "bankbuddy.duplicate_diagnostics.extract_pdf_text",
        lambda _path: BOA_PDF_TEXT,
    )
    paths = resolve_app_paths(home)

    rows = list_duplicate_transaction_diagnostics(paths, account_last4="1145")

    assert len(rows) == 2
