# Transaction List Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add sort, view, and summary controls to `bankbuddy tx list`.

**Architecture:** Keep filtering, sorting, and summary aggregation in `src/bankbuddy/transactions.py`, where transaction query behavior already lives. Keep human-readable output selection in `src/bankbuddy/cli.py`, using typed transaction rows and summaries returned by the query layer. Parse sort fields through a whitelist before building SQL so user input never becomes raw SQL.

**Tech Stack:** Python 3.12, Click, SQLite, pytest, uv.

---

### Task 1: Sort Grammar And Query Ordering

**Files:**
- Modify: `src/bankbuddy/transactions.py`
- Test: `tests/test_transactions.py`

- [x] **Step 1: Write failing tests for sort parsing and query ordering**

Add tests that call `list_transactions(paths, sort=...)` and assert:

```python
rows = list_transactions(paths, sort="amount:desc,date")
assert [row.description for row in rows] == ["PAYROLL", "COFFEE SHOP"]
```

Also add invalid sort tests:

```python
with pytest.raises(TransactionSortError, match="Unsupported sort field"):
    list_transactions(paths, sort="posted_at")
```

- [x] **Step 2: Verify red**

Run: `uv run pytest tests/test_transactions.py -q`

Expected: failures because `list_transactions` does not accept `sort` and `TransactionSortError` does not exist.

- [x] **Step 3: Implement minimal sort support**

Add:

```python
SortDirection = Literal["asc", "desc"]

@dataclass(frozen=True)
class TransactionSort:
    field: str
    direction: SortDirection

class TransactionSortError(ValueError):
    pass
```

Add a parser that accepts comma-separated fields with optional `:asc` / `:desc`, applies `default_order`, rejects unknown fields, and appends `id:asc` as a tie-breaker unless `id` is already present.

- [x] **Step 4: Verify green**

Run: `uv run pytest tests/test_transactions.py -q`

Expected: transaction tests pass.

### Task 2: Summary Aggregation

**Files:**
- Modify: `src/bankbuddy/transactions.py`
- Test: `tests/test_transactions.py`

- [x] **Step 1: Write failing tests for per-currency summaries**

Add tests for:

```python
summary = summarize_transactions(rows)
assert summary["USD"].transaction_count == 2
assert summary["USD"].debit_minor_units == -425
assert summary["USD"].credit_minor_units == 250000
assert summary["USD"].net_minor_units == 249575
```

Also assert filtered debit rows summarize to one debit and zero credits.

- [x] **Step 2: Verify red**

Run: `uv run pytest tests/test_transactions.py -q`

Expected: failure because `summarize_transactions` does not exist.

- [x] **Step 3: Implement summary helper**

Add a frozen dataclass:

```python
@dataclass(frozen=True)
class TransactionSummary:
    currency: str
    transaction_count: int
    debit_minor_units: int
    credit_minor_units: int
    net_minor_units: int
```

Add `summarize_transactions(rows: Iterable[TransactionRow]) -> list[TransactionSummary]` that groups by currency and returns summaries sorted by currency.

- [x] **Step 4: Verify green**

Run: `uv run pytest tests/test_transactions.py -q`

Expected: transaction tests pass.

### Task 3: CLI Sort And View Options

**Files:**
- Modify: `src/bankbuddy/cli.py`
- Test: `tests/test_tx_cli.py`

- [x] **Step 1: Write failing CLI tests**

Add tests for:

```python
result = runner.invoke(main, ["tx", "list", "--sort", "amount:desc"], env=env)
assert result.output.index("PAYROLL") < result.output.index("COFFEE SHOP")
```

Add invalid sort test:

```python
result = runner.invoke(main, ["tx", "list", "--sort", "posted_at"], env=env)
assert result.exit_code != 0
assert "Unsupported sort field" in result.output
```

Add view tests:

```python
result = runner.invoke(main, ["tx", "list", "--view", "compact"], env=env)
assert "Date  Amount  Currency  Description" in result.output
assert "Everyday Checking" not in result.output
```

```python
result = runner.invoke(main, ["tx", "list", "--view", "ledger"], env=env)
assert "ID  Date  Account  Type  Amount  Currency  Description" in result.output
assert "debit" in result.output
assert "credit" in result.output
```

- [x] **Step 2: Verify red**

Run: `uv run pytest tests/test_tx_cli.py -q`

Expected: failures because `--sort`, `--order`, and `--view` are unknown.

- [x] **Step 3: Implement CLI wiring and output views**

Add Click options:

```python
@click.option("--sort", "sort_expression", help="Comma-separated sort fields.")
@click.option("--order", type=click.Choice(["asc", "desc"], case_sensitive=False), default="asc")
@click.option("--view", type=click.Choice(["default", "compact", "ledger"], case_sensitive=False), default="default")
```

Pass sort arguments to `list_transactions`. Catch `TransactionSortError` and raise `click.ClickException`. Extract small rendering helpers for the three views.

- [x] **Step 4: Verify green**

Run: `uv run pytest tests/test_tx_cli.py -q`

Expected: transaction CLI tests pass.

### Task 4: CLI Summary Option And Docs

**Files:**
- Modify: `src/bankbuddy/cli.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`
- Test: `tests/test_tx_cli.py`

- [x] **Step 1: Write failing summary CLI tests**

Add tests for:

```python
result = runner.invoke(main, ["tx", "list", "--summary"], env=env)
assert "Summary" in result.output
assert "Currency  Transactions  Debits  Credits  Net" in result.output
assert "USD  2  -4.25  2500.00  2495.75" in result.output
```

Add a debit-filter summary test:

```python
result = runner.invoke(main, ["tx", "list", "--direction", "debit", "--summary"], env=env)
assert "USD  1  -4.25  0.00  -4.25" in result.output
```

- [x] **Step 2: Verify red**

Run: `uv run pytest tests/test_tx_cli.py -q`

Expected: failure because `--summary` is unknown.

- [x] **Step 3: Implement summary output and docs**

Add `--summary` as a boolean Click option. Render summary after the transaction rows when rows exist. If no rows match, keep `No transactions found.` and do not print an empty summary. Update examples in README and `bank_buddy_spec.md`; add a CHANGELOG entry.

- [x] **Step 4: Verify feature and full suite**

Run:

```bash
uv run pytest tests/test_transactions.py tests/test_tx_cli.py -q
uv run pytest
uv lock --check
git diff --check
./tests/validate.sh
```

Expected: all commands pass.

### Task 5: Publish

**Files:**
- All modified files

- [ ] **Step 1: Commit intentionally**

Run:

```bash
git status --short
git add src/bankbuddy/transactions.py src/bankbuddy/cli.py tests/test_transactions.py tests/test_tx_cli.py README.md CHANGELOG.md bank_buddy_spec.md docs/superpowers/plans/2026-06-14-tx-list-controls.md
git commit -m "Add transaction list controls"
```

- [ ] **Step 2: Push and open PR**

Run:

```bash
git push -u origin enhancement/52-20260614-tx-list-controls
gh pr create --repo codeforester/bankbuddy --base main --head enhancement/52-20260614-tx-list-controls --title "Add transaction list controls" --body "<summary, validation, Closes #52>"
```

- [ ] **Step 3: Merge and cleanup after checks pass**

Run:

```bash
gh pr checks <number> --repo codeforester/bankbuddy --watch
gh pr merge <number> --repo codeforester/bankbuddy --squash --delete-branch
git -C /Users/rameshhp/work/bankbuddy pull --ff-only
git -C /Users/rameshhp/work/bankbuddy worktree remove /Users/rameshhp/work/bankbuddy-worktrees/tx-list-controls
git -C /Users/rameshhp/work/bankbuddy fetch --prune
git -C /Users/rameshhp/work/bankbuddy worktree prune
```

---

## Self-Review

- Spec coverage: sort, order, views, summary, invalid input, docs, and validation are covered.
- Placeholder scan: no TBD/TODO placeholders are present.
- Type consistency: sort and summary names are consistent across tests, query layer, and CLI wiring.
