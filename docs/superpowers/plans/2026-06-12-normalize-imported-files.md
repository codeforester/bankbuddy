# Normalize Imported Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the original imported statement file while copying successful explicit imports into a predictable BankBuddy-managed archive with canonical filenames and traceable database metadata.

**Architecture:** Add nullable metadata columns to `import_files`, derive canonical names from parser-confirmed metadata, and archive successful imports under `processed/<bank-slug>/<year>/<month>/`. Explicit `--file` imports copy into the archive and leave the source file untouched; future inbox scanning can move files from `inbox/` after it owns that workflow.

**Tech Stack:** Python 3.12, Click, SQLite migrations, pytest, uv.

---

### Task 1: Schema And Metadata Contract

**Files:**
- Create: `src/bankbuddy/migrations/0002_import_file_metadata.sql`
- Create: `src/bankbuddy/import_files.py`
- Modify: `tests/test_database.py`
- Test: `tests/test_import_files.py`

- [x] **Step 1: Write failing tests for import file metadata columns and archive helpers**

Expected coverage:
- `schema_migrations` contains `0001_core_schema` and `0002_import_file_metadata`.
- `import_files` has `original_file_name`, `canonical_file_name`, `source_path`, `processed_path`, `statement_start_date`, `statement_end_date`, `account_ref`, and `source_format`.
- Canonical names use `<bank-slug>_<account-ref>_<period-start>_<period-end>.<ext>`.
- Archive paths use `processed/<bank-slug>/<end-year>/<end-month>/<canonical-file-name>`.
- Archiving copies the file and leaves the source path in place.

- [x] **Step 2: Run focused tests and confirm they fail**

Run: `uv run pytest tests/test_database.py tests/test_import_files.py -q`

- [x] **Step 3: Implement migration and archive helper module**

Implementation notes:
- Store source paths as absolute strings from the explicit import path.
- Store processed paths relative to the BankBuddy root, such as `processed/bank-of-america/2026/05/...`.
- Reuse an existing archive file when the destination content hash matches.
- Add a short hash suffix when a canonical destination already exists with different contents.

- [x] **Step 4: Re-run focused tests and confirm they pass**

Run: `uv run pytest tests/test_database.py tests/test_import_files.py -q`

### Task 2: Import Integration

**Files:**
- Modify: `src/bankbuddy/imports.py`
- Modify: `tests/test_imports.py`

- [x] **Step 1: Write failing CSV and PDF import tests**

Expected coverage:
- CSV imports derive the statement period from parsed transaction dates.
- PDF imports derive the statement period from the statement header.
- Imports persist original filename, canonical filename, source path, relative processed path, statement period, last-four account reference, and source format.
- Imports copy the source file into `paths.processed` after account validation and successful parsing.
- Duplicate imports reuse the same import file row and keep canonical metadata stable.

- [x] **Step 2: Run focused import tests and confirm they fail**

Run: `uv run pytest tests/test_imports.py -q`

- [x] **Step 3: Implement parser metadata and persistence updates**

Implementation notes:
- Add a parser helper for Bank of America PDF statement periods.
- Pass source format, statement period, and account reference into `ensure_import_file`.
- Archive only after the import is parseable and the account is validated.
- Keep debug logs to suffixes, counts, and filenames; do not log full account numbers or statement contents.

- [x] **Step 4: Re-run focused import tests and confirm they pass**

Run: `uv run pytest tests/test_imports.py -q`

### Task 3: History, CLI Output, And Docs

**Files:**
- Modify: `src/bankbuddy/import_history.py`
- Modify: `src/bankbuddy/cli.py`
- Modify: `tests/test_import_history.py`
- Modify: `tests/test_import_cli.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`

- [x] **Step 1: Write failing tests for canonical history output**

Expected coverage:
- `list_import_history` returns canonical filename and processed path.
- `bank-buddy import history` shows both the original file and canonical filename without making the default table too wide with full paths.

- [x] **Step 2: Run focused history and CLI tests and confirm they fail**

Run: `uv run pytest tests/test_import_history.py tests/test_import_cli.py -q`

- [x] **Step 3: Implement history query and docs updates**

Implementation notes:
- Add a `Canonical` column to the history output.
- Mention that explicit imports are copied into `~/BankBuddy/processed/...` and originals are left untouched.
- Update the spec to show the year/month archive hierarchy and new `import_files` metadata columns.

- [x] **Step 4: Re-run focused history and CLI tests and confirm they pass**

Run: `uv run pytest tests/test_import_history.py tests/test_import_cli.py -q`

### Task 4: Validation And PR

**Files:**
- All changed files

- [x] **Step 1: Run final validation**

Run:

```bash
uv run pytest -q
./tests/validate.sh
git diff --check
```

- [ ] **Step 2: Commit and open PR**

```bash
git add .
git commit -m "[codex] Normalize imported statement files"
git push -u origin enhancement/19-20260612-normalize-imported-files
gh pr create --repo codeforester/bankbuddy --base main --head enhancement/19-20260612-normalize-imported-files --title "Normalize imported statement files"
```
