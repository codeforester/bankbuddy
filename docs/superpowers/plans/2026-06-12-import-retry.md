# Import Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist supported-file import failures and add `bank-buddy import retry ATTEMPT_ID` so users can retry failed imports after fixing account setup, parser input, or the source file.

**Architecture:** Add nullable `account_id` to `import_attempts` so failed attempts can preserve the selected account when one exists. Record failed attempts at supported importer boundaries (`import_boa_csv`, `import_boa_pdf`, and inbox routing failures before parser dispatch). Add a focused retry module that loads a failed attempt, resolves an existing source path, and invokes the matching importer to create a new success or failure attempt.

**Tech Stack:** Python 3.12, Click, SQLite migrations, pytest, uv.

---

### Task 1: Persist Failure Metadata

**Files:**
- Create: `src/bankbuddy/migrations/0003_import_attempt_account.sql`
- Modify: `src/bankbuddy/imports.py`
- Modify: `src/bankbuddy/import_history.py`
- Modify: `tests/test_imports.py`
- Modify: `tests/test_import_history.py`

- [x] **Step 1: Write failing tests for failed CSV attempt persistence**

Add a test to `tests/test_imports.py` that imports a malformed BOA CSV and expects one failed attempt with source metadata and `account_id`.

```python
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
    csv_path = write_boa_csv(tmp_path, "Date,Description\n06/10/2026,COFFEE SHOP\n")

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
```

- [x] **Step 2: Run the focused failing test**

Run:

```bash
uv run pytest tests/test_imports.py::test_import_boa_csv_records_failed_attempt_on_parse_failure -q
```

Expected: failure because `import_attempts.account_id` does not exist and no failed attempt is recorded.

- [x] **Step 3: Add migration and persistence helpers**

Create `src/bankbuddy/migrations/0003_import_attempt_account.sql`:

```sql
alter table import_attempts add column account_id integer references accounts(account_id);
```

Add `record_failed_import()` and `ensure_import_file_for_attempt()` to `src/bankbuddy/imports.py`. The helper hashes the file, creates or updates an `import_files` row with `file_name`, `file_hash`, `bank_id`, `original_file_name`, `source_path`, and `source_format`, then inserts a failed `import_attempts` row with `finished_at`, `account_id`, and `error_message`.

- [x] **Step 4: Wrap BOA importers**

Update `import_boa_csv()` and `import_boa_pdf()` so `ImportFailure` records a failed attempt before re-raising. The wrappers must not record unsupported suffixes, and successful imports keep their existing behavior.

- [x] **Step 5: Include account id in success attempts and history**

Update the successful `insert into import_attempts` in `import_boa_transactions()` to include `account_id`. Update `ImportHistoryRow` and `list_import_history()` to expose nullable `account_id`. Update `tests/test_import_history.py` expectations for success and synthetic failed rows.

- [x] **Step 6: Run focused tests**

Run:

```bash
uv run pytest tests/test_imports.py tests/test_import_history.py -q
```

Expected: all focused tests pass.

### Task 2: Persist Inbox Routing Failures

**Files:**
- Modify: `src/bankbuddy/inbox.py`
- Modify: `tests/test_inbox.py`

- [x] **Step 1: Write failing inbox failure persistence tests**

Add tests proving that supported inbox failures are recorded and unsupported files are not.

```python
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
            select import_attempts.import_status, import_files.source_format
            from import_attempts
            join import_files using (file_id)
            """
        ).fetchone()
    assert attempt["import_status"] == "failed"
    assert attempt["source_format"] == "boa_pdf"
```

```python
def test_import_inbox_does_not_record_unsupported_files(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    paths.inbox.mkdir(parents=True, exist_ok=True)
    inbox_file = paths.inbox / "notes.txt"
    inbox_file.write_text("unsupported", encoding="utf-8")

    summary = import_inbox(paths)

    assert summary.unsupported_files == 1
    with connect_database(paths) as conn:
        count = conn.execute("select count(*) from import_attempts").fetchone()[0]
    assert count == 0
```

- [x] **Step 2: Run focused failing tests**

Run:

```bash
uv run pytest tests/test_inbox.py -q
```

Expected: the unconfigured PDF persistence test fails because inbox routing failures are currently report-only.

- [x] **Step 3: Record supported inbox routing failures**

Update `src/bankbuddy/inbox.py` to call `record_failed_import()` for CSV account-id-missing failures and PDF account-routing failures. Keep unsupported suffixes report-only.

- [x] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_inbox.py -q
```

Expected: all inbox tests pass.

### Task 3: Add Retry Command

**Files:**
- Create: `src/bankbuddy/import_retry.py`
- Modify: `src/bankbuddy/cli.py`
- Modify: `tests/test_import_cli.py`

- [x] **Step 1: Write failing CLI retry tests**

Add tests that create a failed CSV attempt, fix the source file, run `import retry 1`, and confirm a new success attempt imports rows. Add tests for retrying a success attempt and retrying a missing source file.

- [x] **Step 2: Run focused failing tests**

Run:

```bash
uv run pytest tests/test_import_cli.py -q
```

Expected: failures because `import retry` is not implemented.

- [x] **Step 3: Implement retry module**

Create `src/bankbuddy/import_retry.py` with:

```python
class RetryFailure(ValueError):
    """Raised when a failed import attempt cannot be retried."""
```

and `retry_import_attempt(paths, attempt_id, account_id=None, logger=None) -> ImportSummary`. It should:

- load the attempt and joined `import_files` row;
- require `import_status == "failed"`;
- resolve `source_path` first, then `processed_path` relative to `paths.root`;
- dispatch `boa_csv` to `import_boa_csv()` and require an account id from `--account-id` or the failed attempt;
- dispatch `boa_pdf` to `import_boa_pdf()` using the override account id when provided, stored account id when present, or BOA PDF account auto-routing when absent;
- raise `RetryFailure` for unsupported or missing metadata.

- [x] **Step 4: Add Click command**

Add `bank-buddy import retry ATTEMPT_ID [--account-id ID]` to `src/bankbuddy/cli.py`. Reuse the existing import summary output format and convert `RetryFailure` or `ImportFailure` into `click.ClickException`.

- [x] **Step 5: Run focused CLI tests**

Run:

```bash
uv run pytest tests/test_import_cli.py -q
```

Expected: all import CLI tests pass.

### Task 4: Docs, Spec, And Final Validation

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`
- Modify: `docs/superpowers/plans/2026-06-12-import-retry.md`

- [x] **Step 1: Update docs**

Document:

```bash
uv run bank-buddy import history --status failed
uv run bank-buddy import retry 1
uv run bank-buddy import retry 1 --account-id 1
```

Clarify that retry creates a new attempt and leaves the original failed attempt intact.

- [x] **Step 2: Run full validation**

Run:

```bash
uv run pytest tests/test_imports.py tests/test_inbox.py tests/test_import_cli.py tests/test_import_history.py -q
uv run pytest -q
./tests/validate.sh
git diff --check
```

Expected: all commands exit 0.

- [x] **Step 3: Commit and open PR**

Commit:

```bash
git add README.md CHANGELOG.md bank_buddy_spec.md docs/superpowers/plans/2026-06-12-import-retry.md src/bankbuddy/cli.py src/bankbuddy/import_retry.py src/bankbuddy/imports.py src/bankbuddy/import_history.py src/bankbuddy/inbox.py src/bankbuddy/migrations/0003_import_attempt_account.sql tests/test_import_cli.py tests/test_import_history.py tests/test_imports.py tests/test_inbox.py
git commit -m "[codex] Persist failed imports and add retry"
```

Push and open a PR closing issue #37.
