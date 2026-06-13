# BOA PDF Period Header Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse real Bank of America PDF statement-period headers that use `for <date> to <date> Account number`.

**Architecture:** Keep the existing Bank of America PDF parser boundary. Extend only the statement-period extractor with a second strict header pattern anchored to BOA's `for ... to ... Account number` text, while preserving the existing `Statement Period: ... through ...` behavior.

**Tech Stack:** Python 3.12, Click, SQLite, pytest, pdfplumber.

---

### Task 1: Add The Regression Test

**Files:**
- Modify: `tests/test_imports.py`

- [x] **Step 1: Write a failing test**
  Add a sanitized fixture that includes `for April 22, 2026 to May 19, 2026 Account number: 1234 5678 901145` and assert `extract_boa_pdf_statement_period()` returns `("2026-04-22", "2026-05-19")`.

- [x] **Step 2: Run the focused test**
  Run: `uv run pytest tests/test_imports.py::test_extract_boa_pdf_statement_period_from_account_header -q`
  Expected: fail with `Bank of America PDF is missing a statement period.`

### Task 2: Extend The Extractor

**Files:**
- Modify: `src/bankbuddy/imports.py`
- Test: `tests/test_imports.py`

- [x] **Step 1: Add a second regex pattern**
  Add a pattern that matches `for <Month day, year> to <Month day, year> Account number` with case-insensitive matching.

- [x] **Step 2: Check both patterns in order**
  Update `extract_boa_pdf_statement_period()` to try the existing pattern first, then the account-header pattern.

- [x] **Step 3: Run focused tests**
  Run: `uv run pytest tests/test_imports.py tests/test_import_cli.py tests/test_inbox.py -q`
  Expected: pass.

### Task 3: Validate And Publish

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`

- [x] **Step 1: Document the supported BOA header shape**
- [x] **Step 2: Run full validation**
  Run: `uv run pytest`, `uv lock --check`, `git diff --check`, and `./tests/validate.sh`.
- [ ] **Step 3: Commit, push, open PR, and merge after CI passes**
