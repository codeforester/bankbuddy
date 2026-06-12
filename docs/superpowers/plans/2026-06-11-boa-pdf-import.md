# Bank Of America PDF Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Bank of America text-PDF import path that validates the selected account by full account number before writing transactions.

**Architecture:** Keep account setup explicit with `--account-id`, then route `.pdf` imports to a BOA PDF parser that extracts text with `pdfplumber`, normalizes the PDF account number, and reuses the existing import persistence flow. CSV imports remain supported.

**Tech Stack:** Python 3.12, Click, SQLite, `pdfplumber`, pytest, uv.

---

### Task 1: Parser Contract And Account Validation

**Files:**
- Modify: `tests/test_imports.py`
- Modify: `src/bankbuddy/imports.py`

- [x] Add tests for digit-only account normalization, full-account extraction from space-delimited account header text, PDF transaction parsing, account mismatch rejection, and successful PDF import.
- [x] Run targeted tests and confirm they fail before implementation.
- [x] Implement minimal parsing and validation helpers.
- [x] Re-run targeted tests and confirm they pass.

### Task 2: CLI Routing

**Files:**
- Modify: `tests/test_import_cli.py`
- Modify: `src/bankbuddy/cli.py`

- [x] Add CLI tests proving `.pdf` routes to the PDF importer while `.csv` continues to work.
- [x] Run targeted CLI tests and confirm the PDF test fails first.
- [x] Implement extension-based routing with a clear unsupported-file error.
- [x] Re-run targeted CLI tests and confirm they pass.

### Task 3: Dependencies And Docs

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`

- [x] Add `pdfplumber` as a runtime dependency and refresh `uv.lock`.
- [x] Update documentation from CSV-first to text-PDF-first BOA imports, keeping CSV as supported fallback.
- [x] Run `uv lock --check`, `git diff --check`, targeted tests, and `./tests/validate.sh`.
- [x] Commit, push, and open a PR with `Fixes #17`.
