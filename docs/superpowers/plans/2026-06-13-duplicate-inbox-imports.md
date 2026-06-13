# Duplicate Inbox Imports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skip exact duplicate successful inbox imports before parser work while preserving the duplicate file in a managed `duplicates/` archive.

**Architecture:** Use SHA-256 `file_hash` as the only proof of exact duplication. Add a real `duplicate` import-attempt status and an attempt-level `duplicate_path`, because duplicate copies are per re-drop event while the canonical processed file belongs to the original `import_files` row. Keep successful import canonical metadata as the statement identity and store duplicate physical copies under `duplicates/<bank>/<year>/<month>/`.

**Tech Stack:** Python 3.12, SQLite migrations, Click, pytest, uv.

---

### Task 1: Database And History Contract

**Files:**
- Create: `src/bankbuddy/migrations/0004_duplicate_import_attempts.sql`
- Modify: `tests/test_database.py`
- Modify: `src/bankbuddy/import_history.py`
- Modify: `src/bankbuddy/cli.py`
- Test: `tests/test_import_history.py`

- [x] **Step 1: Write failing migration and history tests**

Add a database test that expects:

```python
assert migration_versions == [
    "0001_core_schema",
    "0002_import_file_metadata",
    "0003_import_attempt_account",
    "0004_duplicate_import_attempts",
]
```

Add a schema test that inserts `import_status = "duplicate"` with `duplicate_path = "duplicates/bank-of-america/2026/06/file.csv"` and expects SQLite to accept it.

Add an import history test that inserts a duplicate attempt and expects `list_import_history()` to expose:

```python
assert row.status == "duplicate"
assert row.processed_path == "processed/bank-of-america/2026/06/file.csv"
assert row.duplicate_path == "duplicates/bank-of-america/2026/06/file.csv"
```

- [x] **Step 2: Run red tests**

Run:

```bash
uv run pytest tests/test_database.py tests/test_import_history.py -q
```

Expected: fail because migration `0004_duplicate_import_attempts` and `ImportHistoryRow.duplicate_path` do not exist.

- [x] **Step 3: Implement migration and history surface**

Create `0004_duplicate_import_attempts.sql` by rebuilding `import_attempts` with:

```sql
import_status text not null check (
    import_status in ('success', 'failed', 'partial', 'duplicate')
),
duplicate_path text,
```

Copy all existing rows with `duplicate_path` as `null`, drop the old table, and rename the new table.

Update `ImportHistoryRow` with `duplicate_path: str | None`, select `import_attempts.duplicate_path`, and update the CLI history header and row output to include `Processed` and `Duplicate` columns.

- [x] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_database.py tests/test_import_history.py tests/test_import_cli.py -q
```

Expected: pass after updating existing CLI history assertions to the wider header.

### Task 2: Duplicate Archive Helpers

**Files:**
- Modify: `src/bankbuddy/paths.py`
- Modify: `src/bankbuddy/import_files.py`
- Test: `tests/test_paths.py`
- Test: `tests/test_import_files.py`

- [x] **Step 1: Write failing archive helper tests**

Add path coverage:

```python
assert paths.duplicates == root / "duplicates"
```

Add duplicate archive coverage:

```python
duplicate_path = archive_duplicate_statement_file(
    paths,
    source_path=inbox_file,
    bank_name="Bank of America",
    statement_end_date="2026-06-11",
    canonical_file_name="bank-of-america_6789_2026-06-10_2026-06-11.csv",
)
assert duplicate_path == (
    "duplicates/bank-of-america/2026/06/"
    "bank-of-america_6789_2026-06-10_2026-06-11.csv"
)
assert (paths.root / duplicate_path).read_text(encoding="utf-8") == source_contents
```

Add a collision test that archives the same canonical duplicate twice and expects the second path to end with `-duplicate-2.csv`.

- [x] **Step 2: Run red tests**

Run:

```bash
uv run pytest tests/test_paths.py tests/test_import_files.py -q
```

Expected: fail because `AppPaths.duplicates` and `archive_duplicate_statement_file()` do not exist.

- [x] **Step 3: Implement archive helpers**

Add `duplicates: Path` to `AppPaths` and create it in `ensure_app_dirs()`.

Add to `import_files.py`:

```python
def duplicate_archive_relative_path(*, bank_name, statement_end_date, canonical_file_name) -> Path:
    ...

def archive_duplicate_statement_file(paths, *, source_path, bank_name, statement_end_date, canonical_file_name) -> str:
    ...
```

The first duplicate uses the existing canonical filename under `duplicates/`. If that destination exists, append `-duplicate-2`, `-duplicate-3`, and so on before the extension until an unused path is found.

- [x] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_paths.py tests/test_import_files.py -q
```

Expected: pass.

### Task 3: Inbox Duplicate Skip Flow

**Files:**
- Modify: `src/bankbuddy/imports.py`
- Modify: `src/bankbuddy/inbox.py`
- Test: `tests/test_inbox.py`

- [x] **Step 1: Write failing inbox tests**

Add a test that imports a CSV successfully, re-drops the exact same content into `inbox/` under a different filename, and runs:

```python
summary = import_inbox(paths)
```

It should pass without `account_id`, proving the duplicate path runs before CSV account validation. Expect:

```python
assert summary.duplicate_files == 1
assert summary.results[0].status == "duplicate"
assert summary.results[0].rows_imported == 0
assert not inbox_file.exists()
assert (paths.root / summary.results[0].duplicate_path).is_file()
```

Add a test that creates a failed-only hash and reruns inbox import with the same file. Expect the file to remain in `inbox/`, no duplicate archive copy, and another failed attempt rather than a duplicate attempt.

- [x] **Step 2: Run red tests**

Run:

```bash
uv run pytest tests/test_inbox.py -q
```

Expected: fail because duplicate detection, duplicate summary counts, and duplicate attempt recording do not exist.

- [x] **Step 3: Implement duplicate detection and attempt recording**

Add import helpers:

```python
@dataclass(frozen=True)
class SuccessfulImportFile:
    file_id: int
    bank_id: int
    bank_name: str
    account_id: int | None
    canonical_file_name: str
    processed_path: str
    statement_end_date: str

def find_successful_import_by_hash(paths, file_hash) -> SuccessfulImportFile | None:
    ...

def record_duplicate_import(paths, duplicate, duplicate_path) -> int:
    ...
```

In `import_inbox()`, after suffix validation and before parser-specific work:

```python
file_hash = statement_imports.hash_file(inbox_file)
duplicate = statement_imports.find_successful_import_by_hash(paths, file_hash)
if duplicate is not None:
    duplicate_path = archive_duplicate_statement_file(...)
    statement_imports.record_duplicate_import(...)
    inbox_file.unlink()
    results.append(InboxFileResult(status="duplicate", ...))
    continue
```

- [x] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_inbox.py tests/test_imports.py -q
```

Expected: pass.

### Task 4: CLI Output And Documentation

**Files:**
- Modify: `src/bankbuddy/cli.py`
- Modify: `README.md`
- Modify: `bank_buddy_spec.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_import_cli.py`

- [x] **Step 1: Write failing CLI tests**

Add CLI coverage for:

```text
Duplicates: 1
duplicate  statement.csv  preserved=duplicates/...
```

Add history CLI coverage that a duplicate row shows `duplicate`, the canonical processed path, and the duplicate path.

- [x] **Step 2: Run red tests**

Run:

```bash
uv run pytest tests/test_import_cli.py -q
```

Expected: fail until CLI output is updated.

- [x] **Step 3: Update CLI and docs**

Update inbox output to include `Duplicates: N`. Keep success lines unchanged. For duplicate results, print:

```text
duplicate  <file>  preserved=<duplicate_path> canonical=<processed_path>
```

Update README and design spec to describe exact SHA-256 duplicate handling and the temporary `duplicates/` preservation policy. Add a changelog entry.

- [x] **Step 4: Final verification**

Run:

```bash
uv run pytest
git diff --check
./tests/validate.sh
uv lock --check
```

Expected: all pass.

- [ ] **Step 5: Commit and PR**

Commit:

```bash
git add .
git commit -m "Skip duplicate inbox imports"
git push -u origin enhancement/43-20260613-duplicate-inbox
```

Open a PR that closes #43.
