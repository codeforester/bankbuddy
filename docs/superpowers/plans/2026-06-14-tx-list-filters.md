# Transaction List Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `bankbuddy tx list` filters for bank name, currency, full account number, and unambiguous account last four digits.

**Architecture:** Keep filtering in `bankbuddy.transactions.list_transactions` so CLI and future callers share one behavior. Resolve account-number filters through configured accounts before building the transaction SQL, because account numbers are stored as entered and should be compared after digit normalization. Keep CLI rendering unchanged so full account numbers are never printed.

**Tech Stack:** Python, Click, SQLite, pytest, uv.

---

### Task 1: Query-Layer Filters

**Files:**
- Modify: `tests/test_transactions.py`
- Modify: `src/bankbuddy/transactions.py`

- [ ] **Step 1: Add failing tests for the new filter arguments**

Add tests that call `list_transactions` with `bank_name`, `currency`, `account_number`, and `account_last4`. Include a missing last4 case and an ambiguous last4 case, both expecting a new filter error type.

- [ ] **Step 2: Run query tests to verify RED**

Run: `uv run pytest tests/test_transactions.py -q`

Expected: FAIL because `list_transactions` does not accept the new keyword arguments and the filter error type does not exist.

- [ ] **Step 3: Implement filter resolution**

In `src/bankbuddy/transactions.py`, add:
- `TransactionFilterError`
- digit normalization for account-number inputs
- account id resolution helpers for exact account number and last four digits
- `banks` join and SQL conditions for bank, currency, and resolved account ids

Use `normalize_currency` for `--currency` parity with account/import validation.

- [ ] **Step 4: Run query tests to verify GREEN**

Run: `uv run pytest tests/test_transactions.py -q`

Expected: PASS.

- [ ] **Step 5: Commit query-layer work**

Run: `git add tests/test_transactions.py src/bankbuddy/transactions.py && git commit -m "feat: add transaction filter queries"`

### Task 2: CLI Filters

**Files:**
- Modify: `tests/test_tx_cli.py`
- Modify: `src/bankbuddy/cli.py`

- [ ] **Step 1: Add failing CLI tests**

Add Click runner tests for:
- `bankbuddy tx list --bank "bank of america"`
- `bankbuddy tx list --currency usd`
- `bankbuddy tx list --account-number "123 456 789"`
- `bankbuddy tx list --account-last4 6789`
- missing and ambiguous `--account-last4`

- [ ] **Step 2: Run CLI tests to verify RED**

Run: `uv run pytest tests/test_tx_cli.py -q`

Expected: FAIL because the new options are not wired.

- [ ] **Step 3: Wire Click options**

In `src/bankbuddy/cli.py`, add the four options to `tx list`, pass them through to `list_transactions`, and catch `TransactionFilterError` with `TransactionSortError`. Log only a masked account suffix for account-number input.

- [ ] **Step 4: Run CLI tests to verify GREEN**

Run: `uv run pytest tests/test_tx_cli.py -q`

Expected: PASS.

- [ ] **Step 5: Commit CLI work**

Run: `git add tests/test_tx_cli.py src/bankbuddy/cli.py && git commit -m "feat: expose transaction filters in CLI"`

### Task 3: Documentation And Validation

**Files:**
- Modify: `README.md`
- Modify: `bank_buddy_spec.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Document the filters**

Update README command examples and the spec transaction-list section with the new filters. Mention that full account numbers can be used for filtering while displayed output remains masked/friendly.

- [ ] **Step 2: Update changelog**

Add a changelog entry for issue #56.

- [ ] **Step 3: Run focused and full validation**

Run:
- `uv run pytest tests/test_transactions.py tests/test_tx_cli.py -q`
- `uv run pytest`
- `uv lock --check`
- `git diff --check`
- `./tests/validate.sh`

Expected: all pass.

- [ ] **Step 4: Commit docs**

Run: `git add README.md bank_buddy_spec.md CHANGELOG.md docs/superpowers/plans/2026-06-14-tx-list-filters.md && git commit -m "docs: describe transaction list filters"`

- [ ] **Step 5: Push and open PR**

Push branch `enhancement/56-20260614-tx-list-filters` and open a PR that closes issue #56.
