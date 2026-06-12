from pathlib import Path

import pytest

from bankbuddy.accounts import add_account
from bankbuddy.database import connect_database
from bankbuddy.imports import ImportFailure
from bankbuddy.imports import extract_boa_pdf_account_number
from bankbuddy.imports import extract_boa_pdf_statement_period
from bankbuddy.imports import extract_pdf_text
from bankbuddy.imports import import_boa_csv
from bankbuddy.imports import import_boa_pdf
from bankbuddy.imports import normalize_account_number
from bankbuddy.imports import parse_boa_csv
from bankbuddy.imports import parse_boa_pdf_text
from bankbuddy.paths import resolve_app_paths


BOA_CSV = """Date,Description,Amount,Running Bal.
06/10/2026,COFFEE SHOP,-4.25,100.00
06/11/2026,PAYROLL,2500.00,2600.00
"""

BOA_PDF_TEXT = """
Bank of America
Account number 1234 5678 901145
Statement Period: June 1, 2026 through June 30, 2026
Transaction activity
Date Description Amount Balance
06/10 COFFEE SHOP -4.25 100.00
06/11 PAYROLL 2,500.00 2,600.00
"""


def write_boa_csv(tmp_path: Path, content: str = BOA_CSV) -> Path:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(content, encoding="utf-8")
    return csv_path


def write_text_pdf(path: Path, lines: list[str]) -> None:
    stream = "\n".join(
        [
            "BT",
            "/F1 12 Tf",
            "72 720 Td",
            "14 TL",
            *pdf_text_lines(lines),
            "ET",
        ]
    ).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(bytes(pdf))


def pdf_text_lines(lines: list[str]) -> list[str]:
    pdf_lines: list[str] = []
    for index, line in enumerate(lines):
        if index:
            pdf_lines.append("T*")
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        pdf_lines.append(f"({escaped}) Tj")
    return pdf_lines


def test_parse_boa_csv_normalizes_rows(tmp_path) -> None:
    csv_path = write_boa_csv(tmp_path)

    rows = parse_boa_csv(csv_path)

    assert len(rows) == 2
    assert rows[0].transaction_date == "2026-06-10"
    assert rows[0].description == "COFFEE SHOP"
    assert rows[0].normalized_description == "coffee shop"
    assert rows[0].amount_minor_units == -425
    assert rows[1].amount_minor_units == 250000


def test_normalize_account_number_keeps_digits_only() -> None:
    assert normalize_account_number("1234 5678 901145") == "12345678901145"
    assert normalize_account_number("Account # 1234-5678-901145") == "12345678901145"


def test_extract_boa_pdf_account_number_from_space_delimited_header() -> None:
    assert extract_boa_pdf_account_number(BOA_PDF_TEXT) == "12345678901145"


def test_extract_boa_pdf_statement_period_from_header() -> None:
    assert extract_boa_pdf_statement_period(BOA_PDF_TEXT) == (
        "2026-06-01",
        "2026-06-30",
    )


def test_extract_pdf_text_reads_synthetic_selectable_pdf(tmp_path) -> None:
    pdf_path = tmp_path / "selectable.pdf"
    write_text_pdf(pdf_path, ["Bank of America", "Account number 1234 5678 901145"])

    text = extract_pdf_text(pdf_path)

    assert "Bank of America" in text
    assert "Account number 1234 5678 901145" in text


def test_parse_boa_pdf_text_normalizes_transactions() -> None:
    rows = parse_boa_pdf_text(BOA_PDF_TEXT)

    assert len(rows) == 2
    assert rows[0].transaction_date == "2026-06-10"
    assert rows[0].description == "COFFEE SHOP"
    assert rows[0].normalized_description == "coffee shop"
    assert rows[0].amount_minor_units == -425
    assert rows[1].transaction_date == "2026-06-11"
    assert rows[1].description == "PAYROLL"
    assert rows[1].amount_minor_units == 250000


def test_parse_boa_pdf_text_accepts_two_digit_years() -> None:
    rows = parse_boa_pdf_text(
        """
        Bank of America
        Account number 1234 5678 901145
        Statement Period: April 23, 2026 through May 19, 2026
        Transaction activity
        Date Description Amount Balance
        04/23/26 GROCERY STORE -42.17 1,200.00
        """
    )

    assert len(rows) == 1
    assert rows[0].transaction_date == "2026-04-23"
    assert rows[0].description == "GROCERY STORE"
    assert rows[0].amount_minor_units == -4217


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
            """
            select
                file_name,
                original_file_name,
                canonical_file_name,
                source_path,
                processed_path,
                statement_start_date,
                statement_end_date,
                account_ref,
                source_format,
                last_success_at
            from import_files
            """
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
    assert file_row["original_file_name"] == "boa.csv"
    assert file_row["canonical_file_name"] == (
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )
    assert file_row["source_path"] == str(csv_path.resolve())
    assert file_row["processed_path"] == (
        "processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )
    assert file_row["statement_start_date"] == "2026-06-10"
    assert file_row["statement_end_date"] == "2026-06-11"
    assert file_row["account_ref"] == "6789"
    assert file_row["source_format"] == "boa_csv"
    assert file_row["last_success_at"] is not None
    assert csv_path.is_file()
    assert (paths.root / file_row["processed_path"]).read_text(encoding="utf-8") == BOA_CSV


def test_import_boa_csv_records_failed_attempt_on_parse_failure(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="123456789",
        account_type="checking",
        currency="USD",
    )
    csv_path = write_boa_csv(
        tmp_path,
        "Date,Description\n06/10/2026,COFFEE SHOP\n",
    )

    with pytest.raises(ImportFailure, match="missing required header"):
        import_boa_csv(paths, csv_path, account_id=account.account_id)

    with connect_database(paths) as conn:
        attempt = conn.execute(
            """
            select
                import_attempts.import_status,
                import_attempts.account_id,
                import_attempts.error_message,
                import_files.file_name,
                import_files.source_path,
                import_files.source_format
            from import_attempts
            join import_files using (file_id)
            """
        ).fetchone()
    assert attempt["import_status"] == "failed"
    assert attempt["account_id"] == account.account_id
    assert "missing required header" in attempt["error_message"]
    assert attempt["file_name"] == "boa.csv"
    assert attempt["source_path"] == str(csv_path.resolve())
    assert attempt["source_format"] == "boa_csv"


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
        file_rows = conn.execute(
            "select canonical_file_name, processed_path from import_files"
        ).fetchall()

    assert first.rows_imported == 2
    assert second.rows_imported == 0
    assert second.rows_skipped_duplicate == 2
    assert transaction_count == 2
    assert [dict(row) for row in file_rows] == [
        {
            "canonical_file_name": "bank-of-america_6789_2026-06-10_2026-06-11.csv",
            "processed_path": (
                "processed/bank-of-america/2026/06/"
                "bank-of-america_6789_2026-06-10_2026-06-11.csv"
            ),
        }
    ]


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


def test_import_boa_pdf_inserts_transactions_after_account_match(tmp_path, monkeypatch) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="12345678901145",
        account_type="checking",
        currency="USD",
    )
    pdf_path = tmp_path / "boa.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 synthetic fixture placeholder")
    monkeypatch.setattr("bankbuddy.imports.extract_pdf_text", lambda _path: BOA_PDF_TEXT)

    summary = import_boa_pdf(paths, pdf_path, account_id=account.account_id)

    assert summary.rows_parsed == 2
    assert summary.rows_imported == 2
    assert summary.rows_skipped_duplicate == 0
    with connect_database(paths) as conn:
        transactions = conn.execute(
            """
            select transaction_date, amount_minor_units, currency, description
            from transactions
            order by transaction_date
            """
        ).fetchall()
        file_row = conn.execute(
            """
            select
                file_name,
                original_file_name,
                canonical_file_name,
                source_path,
                processed_path,
                statement_start_date,
                statement_end_date,
                account_ref,
                source_format
            from import_files
            """
        ).fetchone()
    assert [dict(row) for row in transactions] == [
        {
            "transaction_date": "2026-06-10",
            "amount_minor_units": -425,
            "currency": "USD",
            "description": "COFFEE SHOP",
        },
        {
            "transaction_date": "2026-06-11",
            "amount_minor_units": 250000,
            "currency": "USD",
            "description": "PAYROLL",
        },
    ]
    assert file_row["file_name"] == "boa.pdf"
    assert file_row["original_file_name"] == "boa.pdf"
    assert file_row["canonical_file_name"] == (
        "bank-of-america_1145_2026-06-01_2026-06-30.pdf"
    )
    assert file_row["source_path"] == str(pdf_path.resolve())
    assert file_row["processed_path"] == (
        "processed/bank-of-america/2026/06/"
        "bank-of-america_1145_2026-06-01_2026-06-30.pdf"
    )
    assert file_row["statement_start_date"] == "2026-06-01"
    assert file_row["statement_end_date"] == "2026-06-30"
    assert file_row["account_ref"] == "1145"
    assert file_row["source_format"] == "boa_pdf"
    assert pdf_path.is_file()
    assert (paths.root / file_row["processed_path"]).read_bytes() == (
        b"%PDF-1.4 synthetic fixture placeholder"
    )


def test_import_boa_pdf_rejects_account_number_mismatch(tmp_path, monkeypatch) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="99995678901145",
        account_type="checking",
        currency="USD",
    )
    pdf_path = tmp_path / "boa.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 synthetic fixture placeholder")
    monkeypatch.setattr("bankbuddy.imports.extract_pdf_text", lambda _path: BOA_PDF_TEXT)

    with pytest.raises(ImportFailure, match="does not match configured account"):
        import_boa_pdf(paths, pdf_path, account_id=account.account_id)

    with connect_database(paths) as conn:
        transaction_count = conn.execute("select count(*) from transactions").fetchone()[0]
    assert transaction_count == 0
