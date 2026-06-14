# Transaction Direction Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `bankbuddy tx list --direction debit|credit` so users can inspect outgoing or incoming transactions independently.

**Architecture:** Keep filtering in `bankbuddy.transactions.list_transactions()` where account and date filters already live. The CLI should validate the option with Click and pass the normalized value through; no schema changes are needed.

**Tech Stack:** Python 3.12, Click, SQLite, pytest, uv.

---

### Task 1: Add Transaction Query Coverage

**Files:**
- Modify: `tests/test_transactions.py`
- Modify: `src/bankbuddy/transactions.py`

- [x] **Step 1: Write failing tests**
  Add tests proving `list_transactions(..., direction="debit")` returns negative amounts and `direction="credit"` returns positive amounts, including composition with account/date filters.

- [x] **Step 2: Run focused tests and verify red**
  Run: `uv run pytest tests/test_transactions.py -q`
  Expected: fail because `list_transactions()` does not accept `direction`.

- [x] **Step 3: Implement query filtering**
  Add `direction: Literal["debit", "credit"] | None = None` and translate it to `amount_minor_units < 0` or `> 0`.

- [x] **Step 4: Run focused tests and verify green**
  Run: `uv run pytest tests/test_transactions.py -q`
  Expected: pass.

### Task 2: Add CLI Coverage

**Files:**
- Modify: `tests/test_tx_cli.py`
- Modify: `src/bankbuddy/cli.py`

- [x] **Step 1: Write failing CLI tests**
  Add tests for `bankbuddy tx list --direction debit` and `--direction credit`.

- [x] **Step 2: Run focused CLI tests and verify red**
  Run: `uv run pytest tests/test_tx_cli.py -q`
  Expected: fail because the Click option does not exist.

- [x] **Step 3: Implement CLI option**
  Add `--direction` as `click.Choice(["debit", "credit"])` and pass it to `list_transactions()`.

- [x] **Step 4: Run focused CLI tests and verify green**
  Run: `uv run pytest tests/test_tx_cli.py -q`
  Expected: pass.

### Task 3: Document And Validate

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`

- [x] **Step 1: Document the new filter**
  Add examples and note that debit means negative amount, credit means positive amount.

- [x] **Step 2: Run full validation**
  Run: `uv run pytest`, `uv lock --check`, `git diff --check`, and `./tests/validate.sh`.

- [ ] **Step 3: Commit, push, open PR, and merge after CI passes**
