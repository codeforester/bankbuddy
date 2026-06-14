# Transaction List Format Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `bankbuddy tx list` human-readable by default and add `--format pretty|csv|tsv`.

**Architecture:** Keep transaction query/filter/sort behavior unchanged. Introduce a small rendering layer in `src/bankbuddy/cli.py` that derives column definitions from `--view`, then renders those columns as aligned pretty text, CSV, or TSV. Use Python's standard `csv` module for CSV and TSV escaping, and reject `--summary` with CSV/TSV so machine-readable output remains a single rectangular transaction table.

**Tech Stack:** Python 3.12, Click, standard-library `csv`, pytest, uv.

---

### Task 1: Pretty Output Contract

**Files:**
- Modify: `tests/test_tx_cli.py`
- Modify: `src/bankbuddy/cli.py`

- [ ] **Step 1: Write failing pretty-output tests**

Add tests that assert default output uses aligned columns with a separator line and no longer emits the old double-space debug table:

```python
result = CliRunner().invoke(
    main,
    ["tx", "list"],
    env={"BANKBUDDY_HOME": str(home)},
)

assert "ID  Date" not in result.output
assert "ID | Date       | Account" in result.output
assert "---+" in result.output
assert " 1 | 2026-06-10 | Everyday Checking |  -4.25 | USD" in result.output
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/test_tx_cli.py -q`

Expected: failure because pretty rendering is still the old double-space table.

- [ ] **Step 3: Implement minimal pretty renderer**

Add a `TransactionColumn` dataclass in `src/bankbuddy/cli.py` with `header`, `align`, and `value` fields. Add `transaction_columns(view)` and `render_pretty_rows(rows, columns)` helpers. Make `render_transaction_rows(..., output_format="pretty")` use aligned columns and a separator row.

- [ ] **Step 4: Verify green**

Run: `uv run pytest tests/test_tx_cli.py -q`

Expected: transaction CLI tests pass after updating existing assertions to the pretty format.

### Task 2: CSV And TSV Formats

**Files:**
- Modify: `tests/test_tx_cli.py`
- Modify: `src/bankbuddy/cli.py`

- [ ] **Step 1: Write failing format tests**

Add CSV and TSV tests:

```python
result = CliRunner().invoke(
    main,
    ["tx", "list", "--format", "csv"],
    env={"BANKBUDDY_HOME": str(home)},
)
assert result.output.splitlines()[0] == "id,date,account,amount,currency,description"
assert "1,2026-06-10,Everyday Checking,-4.25,USD,COFFEE SHOP" in result.output
```

```python
result = CliRunner().invoke(
    main,
    ["tx", "list", "--view", "ledger", "--format", "tsv"],
    env={"BANKBUDDY_HOME": str(home)},
)
assert result.output.splitlines()[0] == "id\tdate\taccount\ttype\tamount\tcurrency\tdescription"
assert "1\t2026-06-10\tEveryday Checking\tdebit\t-4.25\tUSD\tCOFFEE SHOP" in result.output
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/test_tx_cli.py -q`

Expected: failure because `--format` is unknown.

- [ ] **Step 3: Implement CSV/TSV rendering**

Add:

```python
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["pretty", "csv", "tsv"], case_sensitive=False),
    default="pretty",
    show_default=True,
    help="Transaction output format.",
)
```

Use `csv.writer` with delimiter `,` for CSV and `\t` for TSV. Use lowercase machine headers from the same column definitions that drive pretty output.

- [ ] **Step 4: Verify green**

Run: `uv run pytest tests/test_tx_cli.py -q`

Expected: transaction CLI tests pass.

### Task 3: Summary Compatibility And Docs

**Files:**
- Modify: `tests/test_tx_cli.py`
- Modify: `src/bankbuddy/cli.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`

- [ ] **Step 1: Write failing summary-format test**

Add:

```python
result = CliRunner().invoke(
    main,
    ["tx", "list", "--format", "csv", "--summary"],
    env={"BANKBUDDY_HOME": str(home)},
)
assert result.exit_code != 0
assert "--summary is only supported with --format pretty" in result.output
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/test_tx_cli.py -q`

Expected: failure because `--format` is unknown or summary is not rejected.

- [ ] **Step 3: Implement validation and docs**

Reject `--summary` when `output_format` is `csv` or `tsv` before querying output. Update README examples, CHANGELOG, and `bank_buddy_spec.md` version/changelog/transaction command docs.

- [ ] **Step 4: Verify feature and full suite**

Run:

```bash
uv run pytest tests/test_tx_cli.py -q
uv run pytest
uv lock --check
git diff --check
./tests/validate.sh
```

Expected: all commands pass.

### Task 4: Publish

**Files:**
- All modified files

- [ ] **Step 1: Commit intentionally**

Run:

```bash
git status --short
git add src/bankbuddy/cli.py tests/test_tx_cli.py README.md CHANGELOG.md bank_buddy_spec.md docs/superpowers/plans/2026-06-14-tx-list-format.md
git diff --cached --check
git commit -m "Improve transaction list formatting"
```

- [ ] **Step 2: Push and open PR**

Run:

```bash
git push -u origin enhancement/54-20260614-tx-list-format
gh pr create --repo codeforester/bankbuddy --base main --head enhancement/54-20260614-tx-list-format --title "Improve transaction list formatting" --body "<summary, validation, Closes #54>"
```

- [ ] **Step 3: Merge and cleanup after checks pass**

Run:

```bash
gh pr checks <number> --repo codeforester/bankbuddy --watch
gh pr merge <number> --repo codeforester/bankbuddy --squash --delete-branch
git -C /Users/rameshhp/work/bankbuddy pull --ff-only
git -C /Users/rameshhp/work/bankbuddy worktree remove /Users/rameshhp/work/bankbuddy-worktrees/tx-list-format
git -C /Users/rameshhp/work/bankbuddy fetch --prune
git -C /Users/rameshhp/work/bankbuddy worktree prune
```

---

## Self-Review

- Spec coverage: pretty default output, CSV, TSV, `--view` composition, summary compatibility, docs, and validation are covered.
- Placeholder scan: no TBD/TODO placeholders are present.
- Type consistency: `output_format`, `TransactionColumn`, and renderer names are used consistently.
