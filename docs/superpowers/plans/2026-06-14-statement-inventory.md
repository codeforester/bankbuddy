# Statement Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `bankbuddy statements summary` and `bankbuddy statements list` so imported statement files can be reviewed by bank, account, year, and month.

**Architecture:** Add a focused `bankbuddy.statements` module that reads successful import metadata and returns typed inventory rows. The CLI adds a new `statements` group that renders pretty tables and delegates filtering/query behavior to the module. The feature is read-only and uses existing `import_files`, `import_attempts`, `accounts`, `banks`, and `transactions` metadata.

**Tech Stack:** Python 3.12, Click, SQLite, pytest, uv.

---

### Task 1: Statement Inventory Query Module

**Files:**
- Create: `src/bankbuddy/statements.py`
- Create: `tests/test_statements.py`

- [ ] **Step 1: Write failing query tests**

Add tests that insert successful statement metadata and transactions, then verify:
- `statement_summary(..., group_by="year")` returns file counts and transaction totals by bank/account/year.
- `statement_summary(..., group_by="month")` splits rows by statement end month.
- `list_statements(...)` returns one row per successful statement file ordered by period.
- `account_last4` must resolve unambiguously.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/test_statements.py -q`

Expected: collection fails because `bankbuddy.statements` does not exist.

- [ ] **Step 3: Implement the query module**

Create dataclasses for `StatementSummaryRow` and `StatementListRow`. Query only successful import attempts with an account and statement period. Count distinct `file_id` values, sum `rows_imported`, sum `rows_skipped_duplicate`, and support `bank`, `account_id`, `account_last4`, and `years` filters.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/test_statements.py -q`

Expected: all statement inventory query tests pass.

### Task 2: CLI Commands

**Files:**
- Create: `tests/test_statements_cli.py`
- Modify: `src/bankbuddy/cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add tests for:
- `bankbuddy statements summary`
- `bankbuddy statements summary --by month --years 2025`
- `bankbuddy statements list --year 2025`
- invalid `--by` values are rejected by Click

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/test_statements_cli.py -q`

Expected: Click reports that `statements` is not a command.

- [ ] **Step 3: Wire the CLI**

Add a `statements` group with `summary` and `list` commands. Parse `--years` for summary and `--year` for list, call the query module, and render pretty tables.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/test_statements.py tests/test_statements_cli.py -q`

Expected: all focused statement inventory tests pass.

### Task 3: Documentation And Validation

**Files:**
- Modify: `README.md`
- Modify: `bank_buddy_spec.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update user docs**

Document `bankbuddy statements summary`, `bankbuddy statements list`, grouping options, and selectors. Explain that the command is read-only and distinct from `audit statements`.

- [ ] **Step 2: Update spec and changelog**

Add the statement inventory command shape to `bank_buddy_spec.md` and add an Unreleased changelog entry for issue #63.

- [ ] **Step 3: Run validation**

Run:
- `uv run pytest tests/test_statements.py tests/test_statements_cli.py -q`
- `./tests/validate.sh`
- `git diff --check`

Expected: all pass.

- [ ] **Step 4: Publish PR**

Push `enhancement/63-20260613-statement-inventory` and open a PR that closes issue #63.
