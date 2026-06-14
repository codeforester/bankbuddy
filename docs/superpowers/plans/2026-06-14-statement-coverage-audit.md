# Statement Coverage Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `bankbuddy audit statements` to report missing, overlapping, duplicate, and covered imported statement periods by account.

**Architecture:** Add a focused `bankbuddy.audit` module that queries successful import metadata and performs deterministic date-window analysis in Python. The CLI delegates selector parsing and rendering to small helpers, mirroring existing `tx list` and `report spending` command patterns. The feature is read-only and does not require a migration because existing import metadata already stores statement periods.

**Tech Stack:** Python 3.12, Click, SQLite, pytest, uv.

---

### Task 1: Audit Engine

**Files:**
- Create: `tests/test_audit.py`
- Create: `src/bankbuddy/audit.py`

- [ ] **Step 1: Write failing engine tests**

Add tests for:
- a continuous statement chain that returns covered rows only
- a missing gap inside a requested window
- overlapping statement periods
- duplicate identical statement periods
- independent windows from `--years 2024,2025`
- ambiguous or missing `account_last4` selector

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/test_audit.py -q`

Expected: collection fails because `bankbuddy.audit` does not exist.

- [ ] **Step 3: Implement the audit module**

Create `src/bankbuddy/audit.py` with dataclasses for audit windows, statement
periods, account summaries, and findings. Query `import_files`, successful
`import_attempts`, `accounts`, and `banks`; filter by account id or resolved
last four digits; analyze inclusive date ranges for covered, missing, overlap,
and duplicate findings.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/test_audit.py -q`

Expected: all audit engine tests pass.

- [ ] **Step 5: Commit audit engine**

Run: `git add src/bankbuddy/audit.py tests/test_audit.py docs/superpowers/specs/2026-06-14-statement-coverage-audit-design.md docs/superpowers/plans/2026-06-14-statement-coverage-audit.md && git commit -m "feat: add statement coverage audit engine"`

### Task 2: CLI Command

**Files:**
- Create: `tests/test_audit_cli.py`
- Modify: `src/bankbuddy/cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add tests for:
- `bankbuddy audit statements --years 2025`
- `bankbuddy audit statements --from 2025-01-01 --to 2025-12-31`
- mutual exclusion between `--years` and `--from/--to`
- requiring `--from` and `--to` together
- `--account-last4` resolution errors

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/test_audit_cli.py -q`

Expected: Click reports that `audit` is not a command.

- [ ] **Step 3: Wire the CLI**

Add an `audit` group and `statements` command. Parse `--years`, `--from`, and
`--to`, call the audit module, and render grouped pretty output. Keep output
human-readable only for the first version.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/test_audit_cli.py tests/test_audit.py -q`

Expected: all focused audit tests pass.

- [ ] **Step 5: Commit CLI work**

Run: `git add src/bankbuddy/cli.py tests/test_audit_cli.py && git commit -m "feat: add statement audit CLI"`

### Task 3: Documentation And Validation

**Files:**
- Modify: `README.md`
- Modify: `bank_buddy_spec.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update user docs**

Document `bankbuddy audit statements`, supported date selectors, and account
selectors. Mention that the command is read-only and uses imported statement
period metadata.

- [ ] **Step 2: Update design spec and changelog**

Bump `bank_buddy_spec.md` and add a changelog entry for issue #58.

- [ ] **Step 3: Run validation**

Run:
- `uv run pytest tests/test_audit.py tests/test_audit_cli.py -q`
- `uv run pytest`
- `uv lock --check`
- `git diff --check`
- `./tests/validate.sh`

Expected: all pass.

- [ ] **Step 4: Commit docs**

Run: `git add README.md bank_buddy_spec.md CHANGELOG.md && git commit -m "docs: describe statement coverage audit"`

- [ ] **Step 5: Publish PR**

Push `enhancement/58-20260614-statement-audit` and open a draft PR that closes issue #58.
