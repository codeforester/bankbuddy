from bankbuddy.accounts import add_account
from bankbuddy.database import connect_database
from bankbuddy.inbox import import_inbox
from bankbuddy.inbox import iter_inbox_files
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
