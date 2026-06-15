# TaxBuddy Document Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build the first TaxBuddy slice: a `taxbuddy` CLI that indexes tax documents, supports dry-run and real imports, archives documents under `tax/processed`, and lists/shows document metadata.

**Architecture:** Keep TaxBuddy code under `src/bankbuddy/tax/` while sharing BankBuddy paths, runtime, SQLite migration runner, and table rendering style. The MVP supports explicit file imports and inbox imports, extracts conservative metadata from text-selectable PDFs or text fixtures, stores no raw text, and uses SHA-256 file hashes for idempotency. Gap detection, expected forms, OCR, synced document roots, and tax calculations remain out of scope for #99.

**Tech Stack:** Python 3.12, Click, SQLite migrations, existing `pdfplumber`-backed `extract_pdf_text`, pytest, `uv`.

---

### Task 1: Schema and Packaging

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/test_packaging.py`
- Create: `src/bankbuddy/migrations/0009_tax_documents.sql`
- Modify: `tests/test_database.py`

- [x] **Step 1: Write failing packaging test**

Update `tests/test_packaging.py` so project scripts must include both CLIs:

```python
assert scripts == {
    "bankbuddy": "bankbuddy.cli:main",
    "taxbuddy": "bankbuddy.tax.cli:main",
}
assert "bank-buddy" not in scripts
```

- [x] **Step 2: Write failing schema test**

Add `test_tax_documents_schema_tracks_imported_document_metadata()` to `tests/test_database.py`. Initialize the database, assert migration `0009_tax_documents` is applied, verify columns on `tax_documents`, insert one row with `file_hash`, `original_file_name`, `canonical_file_name`, `source_path`, `processed_path`, `document_type`, `jurisdiction`, `tax_year`, `source_entity`, `person_label`, and `account_ref`, then assert the row can be read back.

- [x] **Step 3: Run red tests**

Run:

```bash
uv run pytest tests/test_packaging.py tests/test_database.py::test_tax_documents_schema_tracks_imported_document_metadata -q
```

Expected: packaging fails because `taxbuddy` is not declared, and schema fails because `tax_documents` does not exist.

- [x] **Step 4: Add minimal packaging and migration**

Add the `taxbuddy` script entry to `pyproject.toml`. Create `0009_tax_documents.sql`:

```sql
create table tax_documents (
    tax_document_id integer primary key,
    file_hash text not null unique,
    original_file_name text not null,
    canonical_file_name text not null,
    source_path text,
    processed_path text not null,
    document_type text not null,
    jurisdiction text not null,
    tax_year integer not null,
    source_entity text,
    person_label text,
    account_ref text,
    imported_at text not null default current_timestamp,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);
```

- [x] **Step 5: Run green tests**

Run:

```bash
uv run pytest tests/test_packaging.py tests/test_database.py::test_tax_documents_schema_tracks_imported_document_metadata -q
```

Expected: both tests pass.

### Task 2: Tax Document Domain and Metadata Extraction

**Files:**
- Create: `src/bankbuddy/tax/__init__.py`
- Create: `src/bankbuddy/tax/documents.py`
- Create: `tests/test_tax_documents.py`

- [x] **Step 1: Write failing parser and archive-plan tests**

Create tests for:

```python
parse_tax_document_text(
    "Form 1099-INT\nTax Year 2025\nPayer: Bank of America\nAccount number ending in 1234\n"
)
```

Expected metadata: `jurisdiction="US"`, `document_type="1099-INT"`, `tax_year=2025`, `source_entity="Bank of America"`, `account_ref="1234"`.

Also test canonical filename and processed path planning:

```python
plan_tax_document_archive(paths, source_path, metadata, file_hash)
```

Expected canonical filename: `2025_1099-int_bank-of-america_1234.pdf`; expected path: `tax/processed/us/2025/1099-int/2025_1099-int_bank-of-america_1234.pdf`.

- [x] **Step 2: Run red tests**

Run:

```bash
uv run pytest tests/test_tax_documents.py -q
```

Expected: import failure because `bankbuddy.tax.documents` does not exist.

- [x] **Step 3: Implement minimal parser and archive planner**

Implement dataclasses:

```python
TaxDocumentMetadata
TaxDocumentArchivePlan
TaxImportPlan
TaxImportSummary
TaxDocumentRow
```

Implement:

```python
parse_tax_document_text(text: str) -> TaxDocumentMetadata
canonical_tax_document_filename(metadata, suffix=".pdf") -> str
plan_tax_document_archive(paths, source_path, metadata, file_hash) -> TaxDocumentArchivePlan
```

Keep detection conservative: support `1099-INT`, `1099-DIV`, `1099-B`, `W-2`, `Form 26AS`, and `AIS`; support years from `Tax Year YYYY` or `YYYY Form ...`; support source entity from `Payer:`, `Employer:`, `Issuer:`, or `Source:`; support account refs from `ending in ####` or `Account ... ####`.

- [x] **Step 4: Run green tests**

Run:

```bash
uv run pytest tests/test_tax_documents.py -q
```

Expected: parser and archive planner tests pass.

### Task 3: Dry-Run and Real Explicit Imports

**Files:**
- Modify: `src/bankbuddy/tax/documents.py`
- Modify: `tests/test_tax_documents.py`

- [x] **Step 1: Write failing explicit import tests**

Add tests for:

```python
plan_tax_document_import(paths, source_path)
import_tax_document(paths, source_path)
```

Use a `.txt` fixture for deterministic metadata and a monkeypatched PDF extraction test for `.pdf`. Dry-run planning must not create database rows or files. Real import must copy the file to the planned archive path, insert one `tax_documents` row, and return a summary.

Add duplicate test: importing the same file twice returns an idempotent duplicate summary with the original document id and does not create a second row.

- [x] **Step 2: Run red tests**

Run:

```bash
uv run pytest tests/test_tax_documents.py -q
```

Expected: fails because import functions do not exist.

- [x] **Step 3: Implement imports**

Implement:

```python
plan_tax_document_import(paths, source_path) -> TaxImportPlan
import_tax_document(paths, source_path) -> TaxImportSummary
list_tax_documents(paths, year=None, document_type=None) -> list[TaxDocumentRow]
get_tax_document(paths, tax_document_id) -> TaxDocumentRow
```

Use existing `initialize_database`, `connect_database`, and `hash_file`. Read `.txt` directly for fixture support; use existing PDF text extraction for `.pdf`; reject other suffixes with `TaxImportFailure`. Do not persist raw text.

- [x] **Step 4: Run green tests**

Run:

```bash
uv run pytest tests/test_tax_documents.py -q
```

Expected: all tax document domain tests pass.

### Task 4: TaxBuddy CLI

**Files:**
- Create: `src/bankbuddy/tax/cli.py`
- Create: `tests/test_tax_cli.py`
- Modify: `src/bankbuddy/runtime.py`

- [x] **Step 1: Write failing CLI tests**

Add tests for:

```bash
taxbuddy --help
taxbuddy status
taxbuddy import --dry-run --file fixture.txt
taxbuddy import --file fixture.txt
taxbuddy docs list
taxbuddy docs show 1
taxbuddy import --dry-run inbox
```

Use `CliRunner().invoke(tax_main, ...)`. Assert dry-run output includes `Dry run: yes`, metadata, and `Files changed: none`; real import output includes the document id and processed path; list/show output uses the same aligned pretty table style as BankBuddy.

- [x] **Step 2: Run red tests**

Run:

```bash
uv run pytest tests/test_tax_cli.py -q
```

Expected: import failure because `bankbuddy.tax.cli` does not exist.

- [x] **Step 3: Implement CLI and runtime cli_name support**

Update `create_runtime(..., cli_name="bankbuddy")` so `taxbuddy` logs use `taxbuddy` while keeping BankBuddy behavior unchanged. Implement `bankbuddy.tax.cli:main` with Base-style root options, `status`, `import`, `import inbox`, and `docs list/show`.

- [x] **Step 4: Run green tests**

Run:

```bash
uv run pytest tests/test_tax_cli.py tests/test_cli.py -q
```

Expected: TaxBuddy CLI tests pass and BankBuddy runtime tests remain green.

### Task 5: Documentation and Full Validation

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`
- Modify: `docs/superpowers/plans/2026-06-15-tax-document-index.md`

- [x] **Step 1: Update docs**

Document the `taxbuddy` CLI examples, the supported MVP metadata extraction, the read-only dry-run behavior, duplicate-by-hash idempotency, and the `tax/processed/...` archive path.

- [x] **Step 2: Mark plan complete**

Check off completed steps in this plan so future readers can see what happened.

- [x] **Step 3: Run final validation**

Run:

```bash
uv lock --check
git diff --check
uv run pytest -q
./tests/validate.sh
git diff --cached --check
```

Expected: all commands pass.

- [ ] **Step 4: Publish**

Commit, push, create a PR with `Closes #99`, wait for GitHub checks, merge, sync `main`, and remove the temporary worktree.

---

## Plan Self-Review

- Spec coverage: Covers #99 console script, tax paths, migration, explicit and inbox imports, dry-run, metadata detection, canonical archival, duplicate-by-hash idempotency, docs list/show, privacy constraints, and validation. Leaves gap detection, OCR, web UI, spouse sync, expected forms, and tax calculations to later issues.
- Placeholder scan: No TBD/TODO placeholders remain.
- Type consistency: The plan consistently uses `TaxDocumentMetadata`, `TaxDocumentArchivePlan`, `TaxImportPlan`, `TaxImportSummary`, `TaxDocumentRow`, `TaxImportFailure`, and `bankbuddy.tax.cli:main`.
