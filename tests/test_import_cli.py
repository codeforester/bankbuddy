from click.testing import CliRunner

import bankbuddy.imports as imports
from bankbuddy.cli import main
from bankbuddy.database import connect_database
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

APPLE_CARD_PDF_TEXT = """
Statement
Apple Card Customer
Example Person, example@example.com Aug 1 \u2014 Aug 31, 2025
Total Balance $2,474.63
as of Aug 31, 2025
Apple Card is issued by Goldman Sachs Bank USA, Salt Lake City Branch.
Payments
Date Description Amount
08/31/2025 ACH Deposit Internet transfer from account ending in 1145 -$2,479.77
Total payments for this period -$2,479.77
Transactions
Date Description Daily Cash Amount
08/01/2025 APPLE.COM/BILL ONE APPLE PARK WAY 3% $0.30 $9.99
08/03/2025 REFUND MERCHANT 1% $0.10 -$5.00
Total charges, credits and returns $4.99
Daily Cash
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
    ["Account Branch :JAYANAGAR-3RD BLOCK"],
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


def test_import_file_command_reports_summary(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}

    add_result = runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    import_result = runner.invoke(
        main,
        ["import", "--file", str(csv_path), "--account-id", "1"],
        env=env,
    )

    assert add_result.exit_code == 0
    assert import_result.exit_code == 0
    assert "File: boa.csv" in import_result.output
    assert "Rows parsed: 2" in import_result.output
    assert "Rows imported: 2" in import_result.output
    assert "Duplicate rows skipped: 0" in import_result.output


def test_import_file_command_reports_duplicate_summary(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )

    first = runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)
    second = runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Rows imported: 0" in second.output
    assert "Duplicate rows skipped: 2" in second.output


def test_import_file_dry_run_reports_plan_without_writes(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    runner = CliRunner()
    home = tmp_path / "home"
    env = {"BANKBUDDY_HOME": str(home)}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )

    result = runner.invoke(
        main,
        ["import", "--dry-run", "--file", str(csv_path), "--account-id", "1"],
        env=env,
    )

    assert result.exit_code == 0
    assert "Dry run: yes" in result.output
    assert "File: boa.csv" in result.output
    assert "Rows parsed: 2" in result.output
    assert "Rows that would be imported: 2" in result.output
    assert "Rows already present: 0" in result.output
    assert (
        "Processed path: bank/processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    ) in result.output
    assert "Database changed: no" in result.output
    assert "Files changed: none" in result.output
    with connect_database(resolve_app_paths(home)) as conn:
        assert conn.execute("select count(*) from transactions").fetchone()[0] == 0
        assert conn.execute("select count(*) from import_files").fetchone()[0] == 0
        assert conn.execute("select count(*) from import_attempts").fetchone()[0] == 0
    assert not any((home / "processed").rglob("*"))


def test_import_file_dry_run_reports_existing_rows_without_new_attempt(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    runner = CliRunner()
    home = tmp_path / "home"
    env = {"BANKBUDDY_HOME": str(home)}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)

    result = runner.invoke(
        main,
        ["import", "--dry-run", "--file", str(csv_path), "--account-id", "1"],
        env=env,
    )

    assert result.exit_code == 0
    assert "Rows that would be imported: 0" in result.output
    assert "Rows already present: 2" in result.output
    with connect_database(resolve_app_paths(home)) as conn:
        assert conn.execute("select count(*) from transactions").fetchone()[0] == 2
        assert conn.execute("select count(*) from import_files").fetchone()[0] == 1
        assert conn.execute("select count(*) from import_attempts").fetchone()[0] == 1


def test_import_file_dry_run_reports_icici_xls_latest_balance(
    tmp_path,
    monkeypatch,
) -> None:
    xls_path = tmp_path / "icici.xls"
    xls_path.write_bytes(b"synthetic xls placeholder")
    runner = CliRunner()
    home = tmp_path / "home"
    env = {"BANKBUDDY_HOME": str(home)}
    monkeypatch.setattr(
        imports,
        "parse_icici_xls",
        lambda _path: imports.parse_icici_xls_rows(ICICI_XLS_ROWS),
    )
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "ICICI Bank",
            "--country",
            "India",
            "--account-number",
            "123456789012",
            "--type",
            "savings",
            "--currency",
            "INR",
        ],
        env=env,
    )

    result = runner.invoke(
        main,
        ["import", "--dry-run", "--file", str(xls_path), "--account-id", "1"],
        env=env,
    )

    assert result.exit_code == 0
    assert "Dry run: yes" in result.output
    assert "Bank: ICICI Bank | Account ID: 1" in result.output
    assert "Rows parsed: 2" in result.output
    assert "Rows that would be imported: 2" in result.output
    assert (
        "Processed path: bank/processed/icici-bank/2025/04/"
        "icici-bank_9012_2025-04-01_2025-04-30.xls"
    ) in result.output
    assert "Latest balance: INR 24050.25 as of 2025-04-30" in result.output
    assert "Database changed: no" in result.output
    with connect_database(resolve_app_paths(home)) as conn:
        account_row = conn.execute(
            """
            select latest_balance_minor_units, latest_balance_source_file_id
            from accounts
            where account_id = 1
            """
        ).fetchone()
        assert account_row["latest_balance_minor_units"] is None
        assert account_row["latest_balance_source_file_id"] is None
        assert conn.execute("select count(*) from import_files").fetchone()[0] == 0


def test_import_file_dry_run_reports_hdfc_xls_latest_balance(
    tmp_path,
    monkeypatch,
) -> None:
    xls_path = tmp_path / "hdfc.xls"
    xls_path.write_bytes(b"synthetic xls placeholder")
    runner = CliRunner()
    home = tmp_path / "home"
    env = {"BANKBUDDY_HOME": str(home)}
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
        raising=False,
    )
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "HDFC Bank",
            "--country",
            "India",
            "--account-number",
            "123456789356",
            "--type",
            "savings",
            "--currency",
            "INR",
        ],
        env=env,
    )

    result = runner.invoke(
        main,
        ["import", "--dry-run", "--file", str(xls_path), "--account-id", "1"],
        env=env,
    )

    assert result.exit_code == 0
    assert "Dry run: yes" in result.output
    assert "Bank: HDFC Bank | Account ID: 1" in result.output
    assert "Rows parsed: 3" in result.output
    assert "Rows that would be imported: 3" in result.output
    assert (
        "Processed path: bank/processed/hdfc-bank/2025/12/"
        "hdfc-bank_9356_2025-01-01_2025-12-31.xls"
    ) in result.output
    assert "Latest balance: INR 11010.50 as of 2026-01-01" in result.output
    assert "Database changed: no" in result.output


def test_import_file_dry_run_parse_failure_does_not_record_attempt(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text("Date,Description\n06/10/2026,COFFEE SHOP\n", encoding="utf-8")
    runner = CliRunner()
    home = tmp_path / "home"
    env = {"BANKBUDDY_HOME": str(home)}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )

    result = runner.invoke(
        main,
        ["import", "--dry-run", "--file", str(csv_path), "--account-id", "1"],
        env=env,
    )

    assert result.exit_code != 0
    assert "missing required header" in result.output
    with connect_database(resolve_app_paths(home)) as conn:
        assert conn.execute("select count(*) from import_files").fetchone()[0] == 0
        assert conn.execute("select count(*) from import_attempts").fetchone()[0] == 0


def test_import_inbox_command_reports_success_and_removes_source(tmp_path) -> None:
    runner = CliRunner()
    home = tmp_path / "home"
    inbox = home / "bank" / "inbox"
    inbox.mkdir(parents=True)
    inbox_file = inbox / "statement.csv"
    inbox_file.write_text(BOA_CSV, encoding="utf-8")
    env = {"BANKBUDDY_HOME": str(home)}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )

    result = runner.invoke(main, ["import", "inbox", "--account-id", "1"], env=env)

    assert result.exit_code == 0
    assert "Inbox files: 1" in result.output
    assert "Successful: 1" in result.output
    assert "success  statement.csv  parsed=2 imported=2 duplicates=0" in result.output
    assert not inbox_file.exists()


def test_import_inbox_command_dry_run_reports_plan_without_removing_source(
    tmp_path,
) -> None:
    runner = CliRunner()
    home = tmp_path / "home"
    inbox = home / "bank" / "inbox"
    inbox.mkdir(parents=True)
    inbox_file = inbox / "statement.csv"
    inbox_file.write_text(BOA_CSV, encoding="utf-8")
    env = {"BANKBUDDY_HOME": str(home)}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )

    result = runner.invoke(main, ["import", "inbox", "--dry-run", "--account-id", "1"], env=env)

    assert result.exit_code == 0
    assert "Dry run: yes" in result.output
    assert "Inbox files: 1" in result.output
    assert "Planned imports: 1" in result.output
    assert (
        "would-import  statement.csv  parsed=2 would-import=2 duplicates=0  "
        "canonical=bank/processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    ) in result.output
    assert inbox_file.is_file()
    with connect_database(resolve_app_paths(home)) as conn:
        assert conn.execute("select count(*) from transactions").fetchone()[0] == 0
        assert conn.execute("select count(*) from import_files").fetchone()[0] == 0
        assert conn.execute("select count(*) from import_attempts").fetchone()[0] == 0


def test_import_inbox_command_dry_run_routes_icici_xls_by_account_number(
    tmp_path,
    monkeypatch,
) -> None:
    runner = CliRunner()
    home = tmp_path / "home"
    inbox = home / "bank" / "inbox"
    inbox.mkdir(parents=True)
    inbox_file = inbox / "icici-statement.xls"
    inbox_file.write_bytes(b"synthetic xls placeholder")
    env = {"BANKBUDDY_HOME": str(home)}
    monkeypatch.setattr(
        imports,
        "parse_icici_xls",
        lambda _path: imports.parse_icici_xls_rows(ICICI_XLS_ROWS),
    )
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "ICICI Bank",
            "--country",
            "India",
            "--account-number",
            "123456789012",
            "--type",
            "savings",
            "--currency",
            "INR",
        ],
        env=env,
    )

    result = runner.invoke(main, ["import", "inbox", "--dry-run"], env=env)

    assert result.exit_code == 0
    assert "Dry run: yes" in result.output
    assert "Inbox files: 1" in result.output
    assert "Planned imports: 1" in result.output
    assert (
        "would-import  icici-statement.xls  parsed=2 would-import=2 duplicates=0  "
        "canonical=bank/processed/icici-bank/2025/04/"
        "icici-bank_9012_2025-04-01_2025-04-30.xls"
    ) in result.output
    assert inbox_file.is_file()


def test_import_inbox_command_dry_run_routes_hdfc_xls_by_account_number(
    tmp_path,
    monkeypatch,
) -> None:
    runner = CliRunner()
    home = tmp_path / "home"
    inbox = home / "bank" / "inbox"
    inbox.mkdir(parents=True)
    inbox_file = inbox / "hdfc-statement.xls"
    inbox_file.write_bytes(b"synthetic xls placeholder")
    env = {"BANKBUDDY_HOME": str(home)}
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
        raising=False,
    )
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "HDFC Bank",
            "--country",
            "India",
            "--account-number",
            "123456789356",
            "--type",
            "savings",
            "--currency",
            "INR",
        ],
        env=env,
    )

    result = runner.invoke(main, ["import", "inbox", "--dry-run"], env=env)

    assert result.exit_code == 0
    assert "Dry run: yes" in result.output
    assert "Inbox files: 1" in result.output
    assert "Planned imports: 1" in result.output
    assert (
        "would-import  hdfc-statement.xls  parsed=3 would-import=3 duplicates=0  "
        "canonical=bank/processed/hdfc-bank/2025/12/"
        "hdfc-bank_9356_2025-01-01_2025-12-31.xls"
    ) in result.output
    assert inbox_file.is_file()


def test_import_inbox_command_reports_duplicate_file(tmp_path) -> None:
    runner = CliRunner()
    home = tmp_path / "home"
    inbox = home / "bank" / "inbox"
    inbox.mkdir(parents=True)
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    inbox_file = inbox / "statement-redownload.csv"
    inbox_file.write_text(BOA_CSV, encoding="utf-8")
    env = {"BANKBUDDY_HOME": str(home)}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)

    result = runner.invoke(main, ["import", "inbox"], env=env)

    assert result.exit_code == 0
    assert "Inbox files: 1" in result.output
    assert "Successful: 0" in result.output
    assert "Duplicates: 1" in result.output
    assert (
        "duplicate  statement-redownload.csv  "
        "preserved=bank/duplicates/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv  "
        "canonical=bank/processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    ) in result.output
    assert not inbox_file.exists()

    history = runner.invoke(main, ["import", "history", "--status", "duplicate"], env=env)

    assert history.exit_code == 0
    assert "duplicate" in history.output
    assert (
        "bank/processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    ) in history.output
    assert (
        "bank/duplicates/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    ) in history.output


def test_import_inbox_command_dry_run_reports_duplicate_without_move(tmp_path) -> None:
    runner = CliRunner()
    home = tmp_path / "home"
    inbox = home / "bank" / "inbox"
    inbox.mkdir(parents=True)
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    inbox_file = inbox / "statement-redownload.csv"
    inbox_file.write_text(BOA_CSV, encoding="utf-8")
    env = {"BANKBUDDY_HOME": str(home)}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)

    result = runner.invoke(main, ["import", "--dry-run", "inbox"], env=env)

    assert result.exit_code == 0
    assert "Dry run: yes" in result.output
    assert "Planned duplicates: 1" in result.output
    assert (
        "would-skip-duplicate  statement-redownload.csv  "
        "preserved=bank/duplicates/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv  "
        "canonical=bank/processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    ) in result.output
    assert inbox_file.is_file()
    assert not (
        home
        / "bank/duplicates/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    ).exists()
    with connect_database(resolve_app_paths(home)) as conn:
        statuses = [
            row["import_status"]
            for row in conn.execute("select import_status from import_attempts")
        ]
    assert statuses == ["success"]


def test_import_inbox_command_routes_pdf_without_account_id(
    tmp_path,
    monkeypatch,
) -> None:
    runner = CliRunner()
    home = tmp_path / "home"
    inbox = home / "bank" / "inbox"
    inbox.mkdir(parents=True)
    inbox_file = inbox / "statement.pdf"
    inbox_file.write_bytes(b"%PDF-1.4 synthetic fixture placeholder")
    env = {"BANKBUDDY_HOME": str(home)}
    monkeypatch.setattr("bankbuddy.imports.extract_pdf_text", lambda _path: BOA_PDF_TEXT)
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "12345678901145",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )

    result = runner.invoke(main, ["import", "inbox"], env=env)

    assert result.exit_code == 0
    assert "Inbox files: 1" in result.output
    assert "Successful: 1" in result.output
    assert "success  statement.pdf  parsed=2 imported=2 duplicates=0" in result.output
    assert not inbox_file.exists()


def test_import_inbox_command_reports_csv_requires_account_id(tmp_path) -> None:
    runner = CliRunner()
    home = tmp_path / "home"
    inbox = home / "bank" / "inbox"
    inbox.mkdir(parents=True)
    inbox_file = inbox / "statement.csv"
    inbox_file.write_text(BOA_CSV, encoding="utf-8")
    env = {"BANKBUDDY_HOME": str(home)}

    result = runner.invoke(main, ["import", "inbox"], env=env)

    assert result.exit_code == 0
    assert "Failed: 1" in result.output
    assert "failed  statement.csv  CSV inbox import requires --account-id" in result.output
    assert inbox_file.is_file()


def test_import_inbox_command_reports_empty_state(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["import", "inbox", "--account-id", "1"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "No inbox files found." in result.output


def test_import_inbox_command_reports_unsupported_file(tmp_path) -> None:
    runner = CliRunner()
    home = tmp_path / "home"
    inbox = home / "bank" / "inbox"
    inbox.mkdir(parents=True)
    unsupported_file = inbox / "notes.txt"
    unsupported_file.write_text("unsupported", encoding="utf-8")
    env = {"BANKBUDDY_HOME": str(home)}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )

    result = runner.invoke(main, ["import", "inbox", "--account-id", "1"], env=env)

    assert result.exit_code == 0
    assert "Unsupported: 1" in result.output
    assert "unsupported  notes.txt  Unsupported import file type: .txt" in result.output
    assert unsupported_file.is_file()


def test_import_history_command_outputs_attempts(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)

    result = runner.invoke(main, ["import", "history"], env=env)

    assert result.exit_code == 0
    assert (
        "ID  File  Canonical  Processed  Duplicate  Bank  Account  Status  "
        "Started  Finished  Parsed  Imported  Duplicates  Error"
    ) in result.output
    assert (
        "2  boa.csv  bank-of-america_6789_2026-06-10_2026-06-11.csv  "
        "bank/processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv  -  "
        "Bank of America  1  success"
    ) in result.output
    assert "  2  0  2  -" in result.output
    assert (
        "1  boa.csv  bank-of-america_6789_2026-06-10_2026-06-11.csv  "
        "bank/processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv  -  "
        "Bank of America  1  success"
    ) in result.output
    assert "  2  2  0  -" in result.output


def test_import_history_command_filters_by_status_and_limit(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)

    result = runner.invoke(
        main,
        ["import", "history", "--status", "success", "--limit", "1"],
        env=env,
    )

    assert result.exit_code == 0
    assert (
        "2  boa.csv  bank-of-america_6789_2026-06-10_2026-06-11.csv  "
        "bank/processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv  -  "
        "Bank of America  1  success"
    ) in result.output
    assert (
        "1  boa.csv  bank-of-america_6789_2026-06-10_2026-06-11.csv  "
        "bank/processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv  -  "
        "Bank of America  1  success"
    ) not in result.output


def test_import_history_command_reports_empty_state(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["import", "history"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "No import attempts found." in result.output


def test_import_retry_command_retries_failed_csv_attempt(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text("Date,Description\n06/10/2026,COFFEE SHOP\n", encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    failed_import = runner.invoke(
        main,
        ["import", "--file", str(csv_path), "--account-id", "1"],
        env=env,
    )
    csv_path.write_text(BOA_CSV, encoding="utf-8")

    retry_result = runner.invoke(main, ["import", "retry", "1"], env=env)
    history_result = runner.invoke(main, ["import", "history"], env=env)

    assert failed_import.exit_code != 0
    assert "missing required header" in failed_import.output
    assert retry_result.exit_code == 0
    assert "Retried attempt: 1" in retry_result.output
    assert "File: boa.csv" in retry_result.output
    assert "Rows imported: 2" in retry_result.output
    assert history_result.exit_code == 0
    assert "2  boa.csv" in history_result.output
    assert "success" in history_result.output
    assert "1  boa.csv" in history_result.output
    assert "failed" in history_result.output


def test_import_retry_command_rejects_success_attempt(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)

    result = runner.invoke(main, ["import", "retry", "1"], env=env)

    assert result.exit_code != 0
    assert "Only failed import attempts can be retried" in result.output


def test_import_retry_command_reports_missing_source_file(tmp_path) -> None:
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text("Date,Description\n06/10/2026,COFFEE SHOP\n", encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "123456789",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    runner.invoke(main, ["import", "--file", str(csv_path), "--account-id", "1"], env=env)
    csv_path.unlink()

    result = runner.invoke(main, ["import", "retry", "1"], env=env)

    assert result.exit_code != 0
    assert "Source file for attempt 1 is no longer available" in result.output


def test_import_file_command_routes_pdf_imports(tmp_path, monkeypatch) -> None:
    pdf_path = tmp_path / "boa.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 synthetic fixture placeholder")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    monkeypatch.setattr("bankbuddy.imports.extract_pdf_text", lambda _path: BOA_PDF_TEXT)

    add_result = runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "12345678901145",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    import_result = runner.invoke(
        main,
        ["import", "--file", str(pdf_path), "--account-id", "1"],
        env=env,
    )

    assert add_result.exit_code == 0
    assert import_result.exit_code == 0
    assert "File: boa.pdf" in import_result.output
    assert "Rows parsed: 2" in import_result.output
    assert "Rows imported: 2" in import_result.output


def test_import_file_command_routes_apple_card_pdf_imports(
    tmp_path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "apple.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 synthetic fixture placeholder")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}
    monkeypatch.setattr(
        "bankbuddy.imports.extract_pdf_text",
        lambda _path: APPLE_CARD_PDF_TEXT,
    )

    add_result = runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Apple GS",
            "--country",
            "US",
            "--account-number",
            "111122220932",
            "--type",
            "credit_card",
            "--currency",
            "USD",
        ],
        env=env,
    )
    ref_result = runner.invoke(
        main,
        [
            "account",
            "ref",
            "add",
            "--account-id",
            "1",
            "--type",
            "product",
            "--value",
            "Apple Card",
            "--source-format",
            "apple_card_pdf",
        ],
        env=env,
    )
    import_result = runner.invoke(
        main,
        ["import", "--file", str(pdf_path), "--account-id", "1"],
        env=env,
    )

    assert add_result.exit_code == 0
    assert ref_result.exit_code == 0
    assert import_result.exit_code == 0
    assert "File: apple.pdf" in import_result.output
    assert "Bank: Apple Card | Account ID: 1" in import_result.output
    assert "Rows parsed: 3" in import_result.output
    assert "Rows imported: 3" in import_result.output
    with connect_database(resolve_app_paths(tmp_path / "home")) as conn:
        rows = conn.execute(
            """
            select
                transaction_date,
                amount_minor_units,
                currency,
                description
            from transactions
            order by transaction_id
            """
        ).fetchall()
    assert [dict(row) for row in rows] == [
        {
            "transaction_date": "2025-08-31",
            "amount_minor_units": 247977,
            "currency": "USD",
            "description": "ACH Deposit Internet transfer from account ending in 1145",
        },
        {
            "transaction_date": "2025-08-01",
            "amount_minor_units": -999,
            "currency": "USD",
            "description": "APPLE.COM/BILL ONE APPLE PARK WAY",
        },
        {
            "transaction_date": "2025-08-03",
            "amount_minor_units": 500,
            "currency": "USD",
            "description": "REFUND MERCHANT",
        },
    ]


def test_pdf_import_debug_log_omits_full_account_number(tmp_path, monkeypatch) -> None:
    pdf_path = tmp_path / "boa.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 synthetic fixture placeholder")
    log_path = tmp_path / "bankbuddy.log"
    runner = CliRunner()
    env = {
        "BANKBUDDY_HOME": str(tmp_path / "home"),
        "BASE_CACHE_DIR": str(tmp_path / "cache"),
    }
    monkeypatch.setattr("bankbuddy.imports.extract_pdf_text", lambda _path: BOA_PDF_TEXT)

    add_result = runner.invoke(
        main,
        [
            "account",
            "add",
            "--bank",
            "Bank of America",
            "--country",
            "US",
            "--account-number",
            "12345678901145",
            "--type",
            "checking",
            "--currency",
            "USD",
        ],
        env=env,
    )
    import_result = runner.invoke(
        main,
        [
            "--debug",
            "--log-file",
            str(log_path),
            "import",
            "--file",
            str(pdf_path),
            "--account-id",
            "1",
        ],
        env=env,
    )

    assert add_result.exit_code == 0
    assert import_result.exit_code == 0
    assert "Rows imported: 2" in import_result.stdout
    assert "source_format=boa_pdf" in import_result.stderr
    log_text = log_path.read_text(encoding="utf-8")
    assert "rows_parsed=2 rows_imported=2 rows_skipped_duplicate=0" in log_text
    assert "account_suffix=1145" in log_text
    assert "12345678901145" not in log_text
    assert "12345678901145" not in import_result.stderr


def test_import_file_command_rejects_unsupported_file_type(tmp_path) -> None:
    statement_path = tmp_path / "statement.txt"
    statement_path.write_text("not supported", encoding="utf-8")
    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(tmp_path / "home")}

    result = runner.invoke(
        main,
        ["import", "--file", str(statement_path), "--account-id", "1"],
        env=env,
    )

    assert result.exit_code != 0
    assert "Unsupported import file type" in result.output
