from bankbuddy.accounts import add_account
import bankbuddy.imports as imports
from bankbuddy.database import connect_database
from bankbuddy.inbox import import_inbox
from bankbuddy.inbox import iter_inbox_files
from bankbuddy.imports import import_boa_csv
from bankbuddy.paths import resolve_app_paths


BOA_CSV = """Date,Description,Amount,Running Bal.
06/10/2026,COFFEE SHOP,-4.25,100.00
06/11/2026,PAYROLL,2500.00,2600.00
"""


def boa_pdf_text(account_number: str = "123 456 789") -> str:
    return f"""
Bank of America
Account number {account_number}
Statement Period: June 1, 2026 through June 30, 2026
Transaction activity
Date Description Amount Balance
06/10 COFFEE SHOP -4.25 100.00
06/11 PAYROLL 2,500.00 2,600.00
"""


def add_boa_account(paths):
    return add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="123456789",
        account_type="checking",
        currency="USD",
    )


def test_iter_inbox_files_returns_visible_regular_files_sorted(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    paths.inbox.mkdir(parents=True)
    (paths.inbox / "b.csv").write_text("b", encoding="utf-8")
    (paths.inbox / ".hidden.csv").write_text("hidden", encoding="utf-8")
    (paths.inbox / "a.csv").write_text("a", encoding="utf-8")
    (paths.inbox / "nested").mkdir()

    files = iter_inbox_files(paths)

    assert [path.name for path in files] == ["a.csv", "b.csv"]


def test_import_inbox_imports_supported_file_and_removes_source(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "statement.csv"
    inbox_file.write_text(BOA_CSV, encoding="utf-8")

    summary = import_inbox(paths, account_id=account.account_id)

    assert summary.total_files == 1
    assert summary.successful_files == 1
    assert summary.failed_files == 0
    assert summary.unsupported_files == 0
    assert summary.results[0].file_name == "statement.csv"
    assert summary.results[0].status == "success"
    assert summary.results[0].rows_imported == 2
    assert not inbox_file.exists()
    with connect_database(paths) as conn:
        transaction_count = conn.execute("select count(*) from transactions").fetchone()[0]
        processed_path = conn.execute("select processed_path from import_files").fetchone()[0]
    assert transaction_count == 2
    assert (paths.root / processed_path).is_file()


def test_import_inbox_dry_run_reports_supported_file_without_changes(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "statement.csv"
    inbox_file.write_text(BOA_CSV, encoding="utf-8")

    summary = import_inbox(paths, account_id=account.account_id, dry_run=True)

    assert summary.total_files == 1
    assert summary.successful_files == 1
    assert summary.failed_files == 0
    assert summary.results[0].file_name == "statement.csv"
    assert summary.results[0].status == "success"
    assert summary.results[0].message == "Would import"
    assert summary.results[0].rows_parsed == 2
    assert summary.results[0].rows_imported == 2
    assert summary.results[0].rows_skipped_duplicate == 0
    assert summary.results[0].processed_path == (
        "processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )
    assert inbox_file.is_file()
    with connect_database(paths) as conn:
        transaction_count = conn.execute("select count(*) from transactions").fetchone()[0]
        import_file_count = conn.execute("select count(*) from import_files").fetchone()[0]
        attempt_count = conn.execute("select count(*) from import_attempts").fetchone()[0]
    assert transaction_count == 0
    assert import_file_count == 0
    assert attempt_count == 0
    assert not (paths.root / summary.results[0].processed_path).exists()


def test_import_inbox_routes_boa_pdf_by_account_number(tmp_path, monkeypatch) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    add_boa_account(paths)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "statement.pdf"
    inbox_file.write_bytes(b"%PDF synthetic fixture placeholder")
    monkeypatch.setattr(
        "bankbuddy.imports.extract_pdf_text",
        lambda _path: boa_pdf_text(account_number="123 456 789"),
    )

    summary = import_inbox(paths)

    assert summary.total_files == 1
    assert summary.successful_files == 1
    assert summary.failed_files == 0
    assert summary.results[0].file_name == "statement.pdf"
    assert summary.results[0].status == "success"
    assert summary.results[0].rows_imported == 2
    assert not inbox_file.exists()
    with connect_database(paths) as conn:
        transaction_count = conn.execute("select count(*) from transactions").fetchone()[0]
        processed_path = conn.execute("select processed_path from import_files").fetchone()[0]
    assert transaction_count == 2
    assert (paths.root / processed_path).is_file()


def test_import_inbox_routes_statement_by_account_statement_ref(
    tmp_path,
    monkeypatch,
) -> None:
    from bankbuddy.account_refs import add_account_statement_ref

    paths = resolve_app_paths(tmp_path / "home")
    account = add_account(
        paths,
        bank_name="Apple Card",
        country="US",
        account_number="1111",
        account_type="credit_card",
        currency="USD",
    )
    add_account_statement_ref(
        paths,
        account_id=account.account_id,
        ref_type="product",
        ref_value="apple-card",
        source_format="apple_card_pdf",
    )
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "statement.xls"
    inbox_file.write_bytes(b"synthetic statement placeholder")
    parsed_statement = imports.ParsedStatement(
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
    monkeypatch.setattr(
        "bankbuddy.imports.parse_xls_statement",
        lambda _path: (parsed_statement, "apple_card_pdf"),
    )

    summary = import_inbox(paths)

    assert summary.total_files == 1
    assert summary.successful_files == 1
    assert summary.failed_files == 0
    assert summary.results[0].file_name == "statement.xls"
    assert summary.results[0].status == "success"
    assert summary.results[0].rows_imported == 1
    assert not inbox_file.exists()
    with connect_database(paths) as conn:
        transaction = conn.execute(
            "select account_id, currency, amount_minor_units from transactions"
        ).fetchone()
    assert dict(transaction) == {
        "account_id": account.account_id,
        "currency": "USD",
        "amount_minor_units": -1250,
    }


def test_import_inbox_dry_run_reports_duplicate_without_archive_or_history(
    tmp_path,
) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    first_source = tmp_path / "first.csv"
    first_source.write_text(BOA_CSV, encoding="utf-8")
    import_boa_csv(paths, first_source, account_id=account.account_id)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "statement-redownload.csv"
    inbox_file.write_text(BOA_CSV, encoding="utf-8")

    summary = import_inbox(paths, dry_run=True)

    assert summary.total_files == 1
    assert summary.successful_files == 0
    assert summary.duplicate_files == 1
    assert summary.failed_files == 0
    assert summary.results[0].file_name == "statement-redownload.csv"
    assert summary.results[0].status == "duplicate"
    assert summary.results[0].message == (
        "Would skip duplicate of processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )
    assert summary.results[0].processed_path == (
        "processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )
    assert summary.results[0].duplicate_path == (
        "duplicates/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )
    assert inbox_file.is_file()
    assert not (paths.root / summary.results[0].duplicate_path).exists()
    with connect_database(paths) as conn:
        statuses = [
            row["import_status"]
            for row in conn.execute(
                "select import_status from import_attempts order by attempt_id"
            )
        ]
    assert statuses == ["success"]


def test_import_inbox_preserves_successful_duplicate_before_csv_account_check(
    tmp_path,
) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    first_source = tmp_path / "first.csv"
    first_source.write_text(BOA_CSV, encoding="utf-8")
    import_boa_csv(paths, first_source, account_id=account.account_id)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "statement-redownload.csv"
    inbox_file.write_text(BOA_CSV, encoding="utf-8")

    summary = import_inbox(paths)

    assert summary.total_files == 1
    assert summary.successful_files == 0
    assert summary.duplicate_files == 1
    assert summary.failed_files == 0
    assert summary.results[0].file_name == "statement-redownload.csv"
    assert summary.results[0].status == "duplicate"
    assert summary.results[0].rows_imported == 0
    assert summary.results[0].rows_skipped_duplicate == 0
    assert summary.results[0].processed_path == (
        "processed/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )
    assert summary.results[0].duplicate_path == (
        "duplicates/bank-of-america/2026/06/"
        "bank-of-america_6789_2026-06-10_2026-06-11.csv"
    )
    assert not inbox_file.exists()
    assert (paths.root / summary.results[0].duplicate_path).read_text(
        encoding="utf-8"
    ) == BOA_CSV
    with connect_database(paths) as conn:
        transaction_count = conn.execute("select count(*) from transactions").fetchone()[0]
        import_file_count = conn.execute("select count(*) from import_files").fetchone()[0]
        attempts = conn.execute(
            """
            select import_status, rows_parsed, rows_imported, duplicate_path
            from import_attempts
            order by attempt_id
            """
        ).fetchall()

    assert transaction_count == 2
    assert import_file_count == 1
    assert [attempt["import_status"] for attempt in attempts] == [
        "success",
        "duplicate",
    ]
    assert attempts[1]["rows_parsed"] == 0
    assert attempts[1]["rows_imported"] == 0
    assert attempts[1]["duplicate_path"] == summary.results[0].duplicate_path


def test_import_inbox_does_not_skip_failed_only_duplicate_hash(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "bad.csv"
    inbox_file.write_text("Date,Description\n06/10/2026,COFFEE SHOP\n", encoding="utf-8")

    first = import_inbox(paths, account_id=account.account_id)
    second = import_inbox(paths, account_id=account.account_id)

    assert first.failed_files == 1
    assert second.failed_files == 1
    assert second.duplicate_files == 0
    assert inbox_file.is_file()
    assert list(paths.duplicates.rglob("*")) == []
    with connect_database(paths) as conn:
        statuses = [
            row["import_status"]
            for row in conn.execute(
                "select import_status from import_attempts order by attempt_id"
            )
        ]

    assert statuses == ["failed", "failed"]


def test_import_inbox_leaves_unconfigured_pdf_account_in_place(
    tmp_path,
    monkeypatch,
) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "statement.pdf"
    inbox_file.write_bytes(b"%PDF synthetic fixture placeholder")
    monkeypatch.setattr(
        "bankbuddy.imports.extract_pdf_text",
        lambda _path: boa_pdf_text(account_number="999 999 999"),
    )

    summary = import_inbox(paths)

    assert summary.total_files == 1
    assert summary.successful_files == 0
    assert summary.failed_files == 1
    assert summary.results[0].status == "failed"
    assert "No configured account" in summary.results[0].message
    assert inbox_file.is_file()


def test_import_inbox_records_failed_attempt_for_unconfigured_pdf(
    tmp_path,
    monkeypatch,
) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "statement.pdf"
    inbox_file.write_bytes(b"%PDF synthetic fixture placeholder")
    monkeypatch.setattr(
        "bankbuddy.imports.extract_pdf_text",
        lambda _path: boa_pdf_text(account_number="999 999 999"),
    )

    summary = import_inbox(paths)

    assert summary.failed_files == 1
    with connect_database(paths) as conn:
        attempt = conn.execute(
            """
            select
                import_attempts.import_status,
                import_attempts.account_id,
                import_attempts.error_message,
                import_files.source_path,
                import_files.source_format
            from import_attempts
            join import_files using (file_id)
            """
        ).fetchone()
    assert attempt["import_status"] == "failed"
    assert attempt["account_id"] is None
    assert "No configured account" in attempt["error_message"]
    assert attempt["source_path"] == str(inbox_file.resolve())
    assert attempt["source_format"] == "boa_pdf"


def test_import_inbox_requires_account_id_for_csv(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "statement.csv"
    inbox_file.write_text(BOA_CSV, encoding="utf-8")

    summary = import_inbox(paths)

    assert summary.total_files == 1
    assert summary.successful_files == 0
    assert summary.failed_files == 1
    assert summary.results[0].status == "failed"
    assert "requires --account-id" in summary.results[0].message
    assert inbox_file.is_file()


def test_import_inbox_leaves_unsupported_files_in_place(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "notes.txt"
    inbox_file.write_text("unsupported", encoding="utf-8")

    summary = import_inbox(paths, account_id=account.account_id)

    assert summary.total_files == 1
    assert summary.successful_files == 0
    assert summary.unsupported_files == 1
    assert summary.results[0].status == "unsupported"
    assert "Unsupported import file type" in summary.results[0].message
    assert inbox_file.is_file()


def test_import_inbox_does_not_record_unsupported_files(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "notes.txt"
    inbox_file.write_text("unsupported", encoding="utf-8")

    summary = import_inbox(paths)

    assert summary.unsupported_files == 1
    with connect_database(paths) as conn:
        attempt_count = conn.execute("select count(*) from import_attempts").fetchone()[0]
    assert attempt_count == 0
    assert inbox_file.is_file()


def test_import_inbox_leaves_failed_files_in_place(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "bad.csv"
    inbox_file.write_text("not,a,boa,csv\n", encoding="utf-8")

    summary = import_inbox(paths, account_id=account.account_id)

    assert summary.total_files == 1
    assert summary.successful_files == 0
    assert summary.failed_files == 1
    assert summary.results[0].status == "failed"
    assert "missing required header" in summary.results[0].message
    assert inbox_file.is_file()
