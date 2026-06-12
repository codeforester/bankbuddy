# Inbox Auto-Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow `bank-buddy import inbox` to import supported statement files without `--account-id` when the statement metadata can reliably identify a configured account.

**Architecture:** Keep routing inside `bankbuddy.inbox` so the CLI remains a thin presentation layer. Add a narrow account-resolution helper for Bank of America PDFs that extracts the full account number from PDF text, matches it to `accounts.account_number`, and then calls the existing BOA PDF importer with the resolved account id. Keep CSV imports explicit because the current BOA CSV parser has no reliable account metadata.

**Tech Stack:** Python 3.12, Click, SQLite, pdfplumber, pytest, uv.

---

### Task 1: Add Routing Tests For PDF And CSV Inbox Behavior

**Files:**
- Modify: `tests/test_inbox.py`

- [x] **Step 1: Write failing tests for auto-routed BOA PDF imports**

Add tests that create a configured Bank of America account, place a BOA PDF-like file in `paths.inbox`, and call `import_inbox(paths)` without `account_id`.

```python
def test_import_inbox_routes_boa_pdf_by_account_number(tmp_path, monkeypatch) -> None:
    paths = resolve_app_paths(tmp_path)
    add_account(
        paths,
        bank_name="Bank of America",
        account_name="Everyday Checking",
        account_type="checking",
        currency="USD",
        account_number="1234567891145",
    )
    pdf_path = paths.inbox / "statement.pdf"
    paths.inbox.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF")
    monkeypatch.setattr(
        "bankbuddy.imports.extract_pdf_text",
        lambda path: boa_pdf_text(account_number="123 456 789 1145"),
    )

    summary = import_inbox(paths)

    assert summary.successful_files == 1
    assert summary.results[0].status == "success"
    assert not pdf_path.exists()
```

- [x] **Step 2: Write failing tests for missing account and CSV explicitness**

Add tests showing that unknown PDF accounts remain in the inbox and BOA CSV files require an explicit account id when no reliable account metadata is available.

```python
def test_import_inbox_leaves_unconfigured_pdf_account_in_place(tmp_path, monkeypatch) -> None:
    paths = resolve_app_paths(tmp_path)
    pdf_path = paths.inbox / "statement.pdf"
    paths.inbox.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF")
    monkeypatch.setattr(
        "bankbuddy.imports.extract_pdf_text",
        lambda path: boa_pdf_text(account_number="999 999 999 9999"),
    )

    summary = import_inbox(paths)

    assert summary.failed_files == 1
    assert summary.results[0].status == "failed"
    assert "No configured account" in summary.results[0].message
    assert pdf_path.exists()


def test_import_inbox_requires_account_id_for_csv(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)
    csv_path = paths.inbox / "statement.csv"
    paths.inbox.mkdir(parents=True, exist_ok=True)
    csv_path.write_text("Date,Description,Amount\n04/01/2026,Coffee,-4.25\n", encoding="utf-8")

    summary = import_inbox(paths)

    assert summary.failed_files == 1
    assert summary.results[0].status == "failed"
    assert "requires --account-id" in summary.results[0].message
    assert csv_path.exists()
```

- [x] **Step 3: Run the focused tests and confirm RED**

Run:

```bash
uv run pytest tests/test_inbox.py -q
```

Expected: the new tests fail because `import_inbox` still requires keyword-only `account_id`.

### Task 2: Implement Account Resolution In The Inbox Layer

**Files:**
- Modify: `src/bankbuddy/inbox.py`
- Test: `tests/test_inbox.py`

- [x] **Step 1: Add minimal routing helpers**

Add helpers to extract a BOA PDF account number once and resolve it against configured accounts.

```python
def account_id_for_account_number(paths: AppPaths, account_number: str) -> int | None:
    normalized = normalize_account_number(account_number)
    with connect_database(paths) as conn:
        row = conn.execute(
            """
            select account_id
            from accounts
            where account_number = ?
            """,
            (normalized,),
        ).fetchone()
    if row is None:
        return None
    return int(row["account_id"])
```

- [x] **Step 2: Make `account_id` optional for inbox imports**

Change `import_inbox` to accept `account_id: int | None = None`. For PDFs without an explicit account id, extract text, parse the BOA account number, resolve the account id, and pass the text into a PDF importer path that avoids extracting text twice.

- [x] **Step 3: Run focused tests and confirm GREEN**

Run:

```bash
uv run pytest tests/test_inbox.py -q
```

Expected: all inbox tests pass.

### Task 3: Add CLI Coverage For `import inbox` Without `--account-id`

**Files:**
- Modify: `tests/test_import_cli.py`
- Modify: `src/bankbuddy/cli.py`

- [x] **Step 1: Write failing CLI tests**

Add a CLI test that invokes `bank-buddy import inbox` without `--account-id` and confirms a BOA PDF imports through account auto-routing. Add a second test that shows BOA CSV remains in the inbox and reports the explicit-account requirement.

- [x] **Step 2: Run the CLI tests and confirm RED**

Run:

```bash
uv run pytest tests/test_import_cli.py -q
```

Expected: the new CLI tests fail because `--account-id` is currently required.

- [x] **Step 3: Make the Click option optional**

Update the `import inbox` command so `--account-id` is optional and is passed through as `None` when omitted. Keep explicit `--account-id` behavior unchanged.

- [x] **Step 4: Run CLI tests and confirm GREEN**

Run:

```bash
uv run pytest tests/test_import_cli.py -q
```

Expected: all import CLI tests pass.

### Task 4: Update Docs And Validation

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`
- Modify: `docs/superpowers/plans/2026-06-12-inbox-auto-routing.md`

- [x] **Step 1: Document the new behavior**

Update command examples to show:

```bash
uv run bank-buddy import inbox
uv run bank-buddy import inbox --account-id 1
```

Document that BOA PDFs can be auto-routed by account number and BOA CSV still requires `--account-id`.

- [x] **Step 2: Run focused and full validation**

Run:

```bash
uv run pytest tests/test_inbox.py tests/test_import_cli.py -q
uv run pytest -q
./tests/validate.sh
git diff --check
```

Expected: all commands exit 0.

- [x] **Step 3: Commit and open PR**

Commit:

```bash
git add README.md CHANGELOG.md bank_buddy_spec.md docs/superpowers/plans/2026-06-12-inbox-auto-routing.md src/bankbuddy/cli.py src/bankbuddy/inbox.py tests/test_import_cli.py tests/test_inbox.py
git commit -m "[codex] Auto-route inbox imports"
```

Push and open a PR closing issue #35.
