from dataclasses import replace
from pathlib import Path

import pytest

from bankbuddy.accounts import add_account
from bankbuddy.database import connect_database
from bankbuddy.imports import ImportFailure
import bankbuddy.imports as imports
from bankbuddy.imports import extract_boa_pdf_account_number
from bankbuddy.imports import extract_boa_pdf_statement_period
from bankbuddy.imports import extract_pdf_text
from bankbuddy.imports import import_boa_csv
from bankbuddy.imports import import_boa_pdf
from bankbuddy.imports import normalize_account_number
from bankbuddy.imports import parse_boa_csv
from bankbuddy.imports import parse_boa_pdf_text
from bankbuddy.imports import plan_boa_csv_import
from bankbuddy.imports import transaction_hash
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

ICICI_XLS_ROWS = [
    ["ICICI Bank"],
    ["Statement for Account Number", "1234 5678 9012"],
    ["Statement Period", "01/04/2025", "to", "30/04/2025"],
    [
        "Value Date",
        "Transaction Date",
        "Cheque Number",
        "Transaction Remarks",
        "Withdrawal Amount(INR)",
        "Deposit Amount(INR)",
        "Balance(INR)",
    ],
    [
        "01/04/2025",
        "02/04/2025",
        "",
        "ATM CASH WITHDRAWAL",
        "1,000.00",
        "",
        "24,000.00",
    ],
    [
        "30/04/2025",
        "30/04/2025",
        "123456",
        "INTEREST CREDIT",
        "",
        "50.25",
        "24,050.25",
    ],
]

HDFC_XLS_ROWS = [
    ["HDFC BANK Ltd.                                      Statement of accounts"],
    [""],
    ["Account Branch :JAYANAGAR-3RD BLOCK"],
    ["PRIMARY ACCOUNT HOLDER", "Address :LINE 1"],
    ["Cust ID :12345678"],
    ["Nomination  :  Registered", "Account No :123456789356   CLASSIC NR"],
    [
        "Statement From  :  01/01/2025         To  :  31/12/2025",
        "A/C Open Date :02/02/2019",
    ],
    [
        "Date",
        "Narration",
        "Chq./Ref.No.",
        "Value Dt",
        "Withdrawal Amt.",
        "Deposit Amt.",
        "Closing Balance",
    ],
    ["********", "**********************************", "************", "********"],
    [
        "09/01/25",
        "UPI PAYMENT",
        "REF001",
        "09/01/25",
        "500.00",
        "",
        "9,500.00",
    ],
    [
        "31/12/25",
        "RENT RECEIPT",
        "REF002",
        "31/12/25",
        "",
        "1,500.50",
        "11,000.50",
    ],
    [
        "01/01/26",
        "INTEREST CREDIT",
        "REF003",
        "01/01/26",
        "",
        "10.00",
        "11,010.50",
    ],
    ["STATEMENT SUMMARY  :-"],
    ["Opening Balance", "Debits", "Credits", "Closing Bal"],
]


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


def test_parse_icici_xls_rows_normalizes_statement_metadata_and_rows() -> None:
    statement = imports.parse_icici_xls_rows(ICICI_XLS_ROWS)

    assert statement.bank_name == "ICICI Bank"
    assert statement.account_number == "123456789012"
    assert statement.currency == "INR"
    assert statement.statement_start_date == "2025-04-01"
    assert statement.statement_end_date == "2025-04-30"
    assert statement.latest_balance_minor_units == 2405025
    assert statement.latest_balance_as_of_date == "2025-04-30"

    assert len(statement.transactions) == 2
    assert statement.transactions[0].value_date == "2025-04-01"
    assert statement.transactions[0].transaction_date == "2025-04-02"
    assert statement.transactions[0].description == "ATM CASH WITHDRAWAL"
    assert statement.transactions[0].normalized_description == "atm cash withdrawal"
    assert statement.transactions[0].amount_minor_units == -100000
    assert statement.transactions[0].balance_after_minor_units == 2400000
    assert statement.transactions[1].check_number == "123456"
    assert statement.transactions[1].amount_minor_units == 5025


def test_parse_icici_xls_rows_rejects_balance_discontinuity() -> None:
    rows = [list(row) for row in ICICI_XLS_ROWS]
    rows[-1][-1] = "99,999.99"

    with pytest.raises(ImportFailure) as exc_info:
        imports.parse_icici_xls_rows(rows)

    assert "balance does not reconcile" in str(exc_info.value)


def test_parse_icici_xls_rows_treats_zero_filled_amount_column_as_empty() -> None:
    rows = [list(row) for row in ICICI_XLS_ROWS]
    rows[4][5] = "0.00"
    rows[5][4] = "0.00"

    statement = imports.parse_icici_xls_rows(rows)

    assert statement.transactions[0].amount_minor_units == -100000
    assert statement.transactions[1].amount_minor_units == 5025


def test_parse_icici_xls_rows_folds_description_continuation_rows() -> None:
    rows = [list(row) for row in ICICI_XLS_ROWS]
    rows.insert(
        5,
        ["", "", "", "ADDITIONAL REFERENCE DETAILS", "", "", ""],
    )

    statement = imports.parse_icici_xls_rows(rows)

    assert len(statement.transactions) == 2
    assert (
        statement.transactions[0].description
        == "ATM CASH WITHDRAWAL ADDITIONAL REFERENCE DETAILS"
    )
    assert (
        statement.transactions[0].normalized_description
        == "atm cash withdrawal additional reference details"
    )
    assert statement.transactions[0].source_row_key == "5,6"


def test_parse_hdfc_xls_rows_normalizes_metadata_and_boundary_rows() -> None:
    statement = imports.parse_hdfc_xls_rows(HDFC_XLS_ROWS)

    assert statement.bank_name == "HDFC Bank"
    assert statement.account_number == "123456789356"
    assert statement.currency == "INR"
    assert statement.statement_start_date == "2025-01-01"
    assert statement.statement_end_date == "2025-12-31"
    assert statement.latest_balance_minor_units == 1101050
    assert statement.latest_balance_as_of_date == "2026-01-01"

    assert len(statement.transactions) == 3
    assert statement.transactions[0].transaction_date == "2025-01-09"
    assert statement.transactions[0].value_date == "2025-01-09"
    assert statement.transactions[0].description == "UPI PAYMENT"
    assert statement.transactions[0].check_number == "REF001"
    assert statement.transactions[0].amount_minor_units == -50000
    assert statement.transactions[0].balance_after_minor_units == 950000
    assert statement.transactions[1].amount_minor_units == 150050
    assert statement.transactions[2].transaction_date == "2026-01-01"
    assert statement.transactions[2].amount_minor_units == 1000


def test_parse_hdfc_xls_rows_rejects_balance_discontinuity() -> None:
    rows = [list(row) for row in HDFC_XLS_ROWS]
    rows[-3][6] = "99,999.99"

    with pytest.raises(ImportFailure) as exc_info:
        imports.parse_hdfc_xls_rows(rows)

    assert "HDFC XLS balance does not reconcile" in str(exc_info.value)


def test_hdfc_transaction_hash_allows_boundary_row_deduplication() -> None:
    statement = imports.parse_hdfc_xls_rows(HDFC_XLS_ROWS)
    boundary_row = statement.transactions[-1]
    overlapping_boundary_row = replace(boundary_row, source_row_key="99")

    assert transaction_hash(
        boundary_row,
        source_format=imports.HDFC_SOURCE_FORMAT,
    ) == transaction_hash(
        overlapping_boundary_row,
        source_format=imports.HDFC_SOURCE_FORMAT,
    )


def test_import_icici_xls_updates_account_latest_balance(tmp_path, monkeypatch) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    xls_path = tmp_path / "icici.xls"
    xls_path.write_bytes(b"synthetic xls placeholder")
    account = add_account(
        paths,
        bank_name="ICICI Bank",
        country="India",
        account_number="123456789012",
        account_type="savings",
        currency="INR",
        display_name="NRO Savings",
    )
    monkeypatch.setattr(
        imports,
        "parse_icici_xls",
        lambda _path: imports.parse_icici_xls_rows(ICICI_XLS_ROWS),
    )

    summary = imports.import_icici_xls(paths, xls_path, account_id=account.account_id)

    assert summary.bank_name == "ICICI Bank"
    assert summary.rows_parsed == 2
    assert summary.rows_imported == 2
    assert summary.latest_balance_minor_units == 2405025
    assert summary.latest_balance_currency == "INR"
    assert summary.latest_balance_as_of_date == "2025-04-30"
    with connect_database(paths) as conn:
        imported_rows = conn.execute(
            """
            select transaction_date, value_date, amount_minor_units, currency, description
            from transactions
            order by transaction_id
            """
        ).fetchall()
        account_row = conn.execute(
            """
            select
                latest_balance_minor_units,
                latest_balance_currency,
                latest_balance_as_of_date,
                latest_balance_source_file_id
            from accounts
            where account_id = ?
            """,
            (account.account_id,),
        ).fetchone()
        file_row = conn.execute(
            "select file_id, source_format from import_files"
        ).fetchone()

    assert [tuple(row) for row in imported_rows] == [
        ("2025-04-02", "2025-04-01", -100000, "INR", "ATM CASH WITHDRAWAL"),
        ("2025-04-30", "2025-04-30", 5025, "INR", "INTEREST CREDIT"),
    ]
    assert account_row["latest_balance_minor_units"] == 2405025
    assert account_row["latest_balance_currency"] == "INR"
    assert account_row["latest_balance_as_of_date"] == "2025-04-30"
    assert account_row["latest_balance_source_file_id"] == file_row["file_id"]
    assert file_row["source_format"] == "icici_xls"


def test_import_xls_statement_persists_hdfc_rows_and_latest_balance(
    tmp_path,
    monkeypatch,
) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    xls_path = tmp_path / "hdfc.xls"
    xls_path.write_bytes(b"synthetic xls placeholder")
    account = add_account(
        paths,
        bank_name="HDFC Bank",
        country="India",
        account_number="123456789356",
        account_type="savings",
        currency="INR",
        display_name="HDFC Savings",
    )
    monkeypatch.setattr(
        imports,
        "parse_icici_xls",
        lambda _path: (_ for _ in ()).throw(
            imports.ImportFailure("not an ICICI statement")
        ),
    )
    monkeypatch.setattr(
        imports,
        "parse_hdfc_xls",
        lambda _path: imports.parse_hdfc_xls_rows(HDFC_XLS_ROWS),
    )

    summary = imports.import_xls_statement(
        paths,
        xls_path,
        account_id=account.account_id,
    )

    assert summary.bank_name == "HDFC Bank"
    assert summary.rows_parsed == 3
    assert summary.rows_imported == 3
    assert summary.latest_balance_minor_units == 1101050
    assert summary.latest_balance_currency == "INR"
    assert summary.latest_balance_as_of_date == "2026-01-01"
    with connect_database(paths) as conn:
        account_row = conn.execute(
            """
            select
                latest_balance_minor_units,
                latest_balance_currency,
                latest_balance_as_of_date,
                latest_balance_source_file_id
            from accounts
            where account_id = ?
            """,
            (account.account_id,),
        ).fetchone()
        file_row = conn.execute(
            "select file_id, source_format from import_files"
        ).fetchone()

    assert account_row["latest_balance_minor_units"] == 1101050
    assert account_row["latest_balance_currency"] == "INR"
    assert account_row["latest_balance_as_of_date"] == "2026-01-01"
    assert account_row["latest_balance_source_file_id"] == file_row["file_id"]
    assert file_row["source_format"] == "hdfc_xls"


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


def test_extract_boa_pdf_statement_period_from_account_header() -> None:
    assert extract_boa_pdf_statement_period(
        """
        Bank of America
        for April 22, 2026 to May 19, 2026 Account number: 1234 5678 901145
        Beginning balance on April 22, 2026 $1,234.56
        Ending balance on May 19, 2026 $2,345.67
        """
    ) == (
        "2026-04-22",
        "2026-05-19",
    )


def test_extract_boa_pdf_statement_period_from_combined_statement_header() -> None:
    assert extract_boa_pdf_statement_period(
        """
        Bank of America
        Your combined statement
        for March 21, 2019 to April 19, 2019
        Your deposit accounts Account/plan number Ending balance Details on
        Account number: 1234 5678 901145
        """
    ) == (
        "2019-03-21",
        "2019-04-19",
    )


def test_extract_boa_pdf_statement_period_from_legacy_page_header() -> None:
    assert extract_boa_pdf_statement_period(
        """
        Bank of America
        Customer Name ! Account # 1234 5678 901145 ! March 21, 2019 to April 19, 2019
        Account number: 1234 5678 901145
        Account summary
        """
    ) == (
        "2019-03-21",
        "2019-04-19",
    )


def test_extract_boa_pdf_statement_period_failure_explains_supported_headers() -> None:
    with pytest.raises(ImportFailure) as exc_info:
        extract_boa_pdf_statement_period(
            """
            Bank of America
            Account number: 1234 5678 901145
            Account summary
            """
        )

    assert "statement period was not found" in str(exc_info.value)
    assert "Your combined statement" in str(exc_info.value)


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


def test_parse_boa_pdf_text_folds_continuation_lines_into_description() -> None:
    rows = parse_boa_pdf_text(
        """
        Bank of America
        Account number 1234 5678 901145
        Statement Period: January 1, 2026 through January 31, 2026
        Transaction activity
        Date Description Amount
        01/20/26 Isha Foundation DES:DEBITS ID:Rpadmanabhaiah INDN:Ramesh Padmanabhaiah CO -100.00
        ID:123456789 PPD
        01/20/26 Isha Foundation DES:DEBITS ID:Rpadmanabhaiah INDN:Ramesh Padmanabhaiah CO -100.00
        ID:987654321 PPD
        """
    )

    assert len(rows) == 2
    assert rows[0].description.endswith("ID:123456789 PPD")
    assert rows[1].description.endswith("ID:987654321 PPD")
    assert rows[0].normalized_description != rows[1].normalized_description


def test_boa_pdf_transaction_hash_distinguishes_continuation_lines() -> None:
    rows = parse_boa_pdf_text(
        """
        Bank of America
        Account number 1234 5678 901145
        Statement Period: January 1, 2026 through January 31, 2026
        Transaction activity
        Date Description Amount
        01/20/26 BARCLAYCARD US DES:CREDITCARD ID:XXXXXXXXX INDN:SUDHA NAGENDRA CO -176.70
        ID:111111111 WEB
        01/20/26 BARCLAYCARD US DES:CREDITCARD ID:XXXXXXXXX INDN:SUDHA NAGENDRA CO -176.70
        ID:222222222 WEB
        """
    )

    hashes = [transaction_hash(row, source_format="boa_pdf") for row in rows]

    assert len(set(hashes)) == 2


def test_boa_pdf_transaction_hash_distinguishes_identical_statement_rows() -> None:
    rows = parse_boa_pdf_text(
        """
        Bank of America
        Account number 1234 5678 901145
        Statement Period: January 1, 2026 through January 31, 2026
        Transaction activity
        Date Description Amount
        01/20/26 Isha Foundation DES:DEBITS ID:Rpadmanabhaiah INDN:Ramesh Padmanabhaiah CO -100.00
        ID:123456789 PPD
        01/20/26 Isha Foundation DES:DEBITS ID:Rpadmanabhaiah INDN:Ramesh Padmanabhaiah CO -100.00
        ID:123456789 PPD
        """
    )

    hashes = [transaction_hash(row, source_format="boa_pdf") for row in rows]

    assert rows[0].source_row_key != rows[1].source_row_key
    assert len(set(hashes)) == 2


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


def test_plan_boa_csv_import_reports_would_import_without_writes(tmp_path) -> None:
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

    plan = plan_boa_csv_import(paths, csv_path, account_id=account.account_id)

    assert plan.file_name == "boa.csv"
    assert plan.bank_name == "Bank of America"
    assert plan.account_id == account.account_id
    assert plan.rows_parsed == 2
    assert plan.rows_would_import == 2
    assert plan.rows_already_present == 0
    assert plan.processed_path == (
        "processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )
    with connect_database(paths) as conn:
        assert conn.execute("select count(*) from transactions").fetchone()[0] == 0
        assert conn.execute("select count(*) from import_files").fetchone()[0] == 0
        assert conn.execute("select count(*) from import_attempts").fetchone()[0] == 0
    assert not (paths.root / plan.processed_path).exists()


def test_plan_boa_csv_import_reports_existing_transaction_duplicates(tmp_path) -> None:
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
    import_boa_csv(paths, csv_path, account_id=account.account_id)

    plan = plan_boa_csv_import(paths, csv_path, account_id=account.account_id)

    assert plan.rows_parsed == 2
    assert plan.rows_would_import == 0
    assert plan.rows_already_present == 2
    with connect_database(paths) as conn:
        assert conn.execute("select count(*) from transactions").fetchone()[0] == 2
        assert conn.execute("select count(*) from import_files").fetchone()[0] == 1
        assert conn.execute("select count(*) from import_attempts").fetchone()[0] == 1


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


def test_import_parsed_statement_rejects_explicit_account_id_mapped_to_other_ref(
    tmp_path,
) -> None:
    from bankbuddy.account_refs import add_account_statement_ref

    paths = resolve_app_paths(tmp_path / "home")
    first_account = add_account(
        paths,
        bank_name="Apple Card",
        country="US",
        account_number="1111",
        account_type="credit_card",
        currency="USD",
    )
    second_account = add_account(
        paths,
        bank_name="Apple Card",
        country="US",
        account_number="2222",
        account_type="credit_card",
        currency="USD",
    )
    add_account_statement_ref(
        paths,
        account_id=first_account.account_id,
        ref_type="product",
        ref_value="apple-card",
        source_format="apple_card_pdf",
    )
    statement = imports.ParsedStatement(
        bank_name="Apple Card",
        account_number="",
        currency="USD",
        statement_start_date="2026-03-01",
        statement_end_date="2026-03-31",
        transactions=[
            imports.ParsedTransaction(
                transaction_date="2026-03-15",
                amount_minor_units=-1250,
                description="CARD PURCHASE",
                normalized_description="card purchase",
                check_number=None,
                source_row_key="1",
            )
        ],
        statement_refs=(
            imports.StatementAccountRef(
                ref_type="product",
                ref_value="apple-card",
            ),
        ),
    )
    source_path = tmp_path / "apple.pdf"
    source_path.write_bytes(b"%PDF synthetic fixture placeholder")

    with pytest.raises(ImportFailure, match="maps to account 1, not account 2"):
        imports.import_parsed_statement(
            paths,
            source_path,
            account_id=second_account.account_id,
            parsed_statement=statement,
            source_format="apple_card_pdf",
            import_label="PDF",
        )

    with connect_database(paths) as conn:
        transaction_count = conn.execute("select count(*) from transactions").fetchone()[0]

    assert transaction_count == 0
