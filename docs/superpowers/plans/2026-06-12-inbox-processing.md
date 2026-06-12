# Inbox Processing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `bank-buddy import inbox --account-id ACCOUNT_ID` so BankBuddy can process statement files placed in the managed inbox directory.

**Architecture:** Add a focused `bankbuddy.inbox` module that discovers non-hidden regular files in `paths.inbox`, imports supported CSV/PDF files through the existing explicit import pipeline, and removes successfully imported inbox-owned files after the canonical archive copy has been written. Unsupported and failed files remain in `inbox` with per-file status. This slice requires a single explicit account id; account auto-detection and multi-account routing remain later work.

**Tech Stack:** Python 3.12, Click, SQLite, pytest, uv.

---

### Task 1: Inbox Processing Service

**Files:**
- Create: `src/bankbuddy/inbox.py`
- Test: `tests/test_inbox.py`

- [x] **Step 1: Write failing inbox service tests**

Create `tests/test_inbox.py`:

```python
from pathlib import Path

from bankbuddy.accounts import add_account
from bankbuddy.database import connect_database
from bankbuddy.inbox import import_inbox
from bankbuddy.inbox import iter_inbox_files
from bankbuddy.paths import resolve_app_paths


BOA_CSV = """Date,Description,Amount,Running Bal.
06/10/2026,COFFEE SHOP,-4.25,100.00
06/11/2026,PAYROLL,2500.00,2600.00
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
```

- [x] **Step 2: Run focused tests and confirm they fail**

Run: `uv run pytest tests/test_inbox.py -q`

Expected: import failure because `bankbuddy.inbox` does not exist.

- [x] **Step 3: Implement the inbox service**

Create `src/bankbuddy/inbox.py` with:
- `InboxFileResult`
- `InboxImportSummary`
- `iter_inbox_files(paths)`
- `import_inbox(paths, account_id, logger=None)`

Implementation rules:
- Call `initialize_database(paths)` before scanning.
- Ignore hidden files and directories.
- Dispatch `.csv` to `import_boa_csv`, `.pdf` to `import_boa_pdf`.
- Catch `ImportFailure` and leave the source file in place.
- Leave unsupported file types in place.
- Remove a source inbox file only after the explicit importer returns success.

- [x] **Step 4: Re-run focused tests and confirm they pass**

Run: `uv run pytest tests/test_inbox.py -q`

Expected: all inbox service tests pass.

### Task 2: Inbox CLI

**Files:**
- Modify: `src/bankbuddy/cli.py`
- Test: `tests/test_import_cli.py`

- [x] **Step 1: Write failing CLI tests**

Add tests to `tests/test_import_cli.py`:

```python
def test_import_inbox_command_reports_success_and_removes_source(tmp_path) -> None:
    runner = CliRunner()
    home = tmp_path / "home"
    inbox = home / "inbox"
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
    inbox = home / "inbox"
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
```

- [x] **Step 2: Run focused CLI tests and confirm they fail**

Run: `uv run pytest tests/test_import_cli.py -q`

Expected: Click reports no `inbox` command under `import`.

- [x] **Step 3: Implement the CLI command**

Modify `src/bankbuddy/cli.py`:
- Import `import_inbox`.
- Add `@import_command.command("inbox")`.
- Require `--account-id`.
- Print aggregate counts and per-file result rows.
- Use runtime debug logging for counts only.

- [x] **Step 4: Re-run focused CLI tests and confirm they pass**

Run: `uv run pytest tests/test_import_cli.py -q`

Expected: import CLI tests pass.

### Task 3: Docs And Validation

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`
- Modify: `docs/superpowers/plans/2026-06-12-inbox-processing.md`

- [x] **Step 1: Document inbox usage**

Add examples:

```bash
uv run bank-buddy import inbox --account-id 1
```

Update the design spec changelog and import-flow section to note explicit account-id inbox processing and successful inbox source removal.

- [x] **Step 2: Run final validation**

Run:

```bash
uv run pytest -q
./tests/validate.sh
git diff --check
```

Expected: all commands pass.

- [ ] **Step 3: Commit and open PR**

```bash
git add .
git commit -m "[codex] Add inbox import processing"
git push -u origin enhancement/33-20260612-inbox-processing
gh pr create --repo codeforester/bankbuddy --base main --head enhancement/33-20260612-inbox-processing --title "Add inbox import processing"
```
