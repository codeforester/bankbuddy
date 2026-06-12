# Spending Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `bank-buddy report spending` so imported transactions can be summarized by period, category, and currency without opening SQLite directly.

**Architecture:** Add a focused `bankbuddy.reports` query module that returns spending summary rows from the existing transaction schema. Add a Click `report` command group with a `spending` subcommand that validates year/month inputs, calls the query module, and prints a stable text table. Spending means outgoing transactions where `amount_minor_units < 0`, excluding confirmed transfers, grouped by currency and category so current Uncategorized imports remain visible.

**Tech Stack:** Python 3.12, Click, SQLite, pytest, uv.

---

### Task 1: Spending Report Query

**Files:**
- Create: `src/bankbuddy/reports.py`
- Test: `tests/test_reports.py`

- [x] **Step 1: Write failing tests for yearly and monthly spending summaries**

Create `tests/test_reports.py`:

```python
from pathlib import Path

from bankbuddy.accounts import Account
from bankbuddy.accounts import add_account
from bankbuddy.database import connect_database
from bankbuddy.imports import import_boa_csv
from bankbuddy.paths import AppPaths
from bankbuddy.paths import resolve_app_paths
from bankbuddy.reports import spending_report


BOA_CSV = """Date,Description,Amount,Running Bal.
05/19/2026,GROCERY STORE,-42.17,100.00
06/10/2026,COFFEE SHOP,-4.25,95.75
06/11/2026,PAYROLL,2500.00,2595.75
"""

SECOND_BOA_CSV = """Date,Description,Amount,Running Bal.
06/12/2026,BOOK STORE,-19.99,100.00
"""


def write_csv(tmp_path: Path, name: str, content: str) -> Path:
    csv_path = tmp_path / name
    csv_path.write_text(content, encoding="utf-8")
    return csv_path


def add_boa_account(paths: AppPaths, *, account_number: str) -> Account:
    return add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number=account_number,
        account_type="checking",
        currency="USD",
    )


def test_spending_report_groups_outgoing_transactions_by_currency_and_category(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    first_account = add_boa_account(paths, account_number="123456789")
    second_account = add_boa_account(paths, account_number="987654321")
    import_boa_csv(
        paths,
        write_csv(tmp_path, "first.csv", BOA_CSV),
        account_id=first_account.account_id,
    )
    import_boa_csv(
        paths,
        write_csv(tmp_path, "second.csv", SECOND_BOA_CSV),
        account_id=second_account.account_id,
    )

    rows = spending_report(paths, year=2026)

    assert [row.currency for row in rows] == ["USD"]
    assert rows[0].category_name == "Uncategorized"
    assert rows[0].transaction_count == 3
    assert rows[0].spending_minor_units == 6641


def test_spending_report_filters_to_month(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(paths, write_csv(tmp_path, "boa.csv", BOA_CSV), account_id=account.account_id)

    rows = spending_report(paths, year=2026, month=6)

    assert len(rows) == 1
    assert rows[0].transaction_count == 1
    assert rows[0].spending_minor_units == 425


def test_spending_report_excludes_confirmed_transfers(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths, account_number="123456789")
    import_boa_csv(paths, write_csv(tmp_path, "boa.csv", BOA_CSV), account_id=account.account_id)
    with connect_database(paths) as conn:
        conn.execute(
            "update transactions set transfer_status = 'confirmed' where description = ?",
            ("COFFEE SHOP",),
        )
        conn.commit()

    rows = spending_report(paths, year=2026, month=6)

    assert rows == []
```

- [x] **Step 2: Run focused tests and confirm they fail**

Run: `uv run pytest tests/test_reports.py -q`

Expected: import failure because `bankbuddy.reports` does not exist.

- [x] **Step 3: Implement the query module**

Create `src/bankbuddy/reports.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from bankbuddy.database import connect_database, initialize_database
from bankbuddy.paths import AppPaths


@dataclass(frozen=True)
class SpendingReportRow:
    category_name: str
    currency: str
    transaction_count: int
    spending_minor_units: int


def spending_report(
    paths: AppPaths,
    *,
    year: int,
    month: int | None = None,
) -> list[SpendingReportRow]:
    initialize_database(paths)
    date_from = f"{year:04d}-{month or 1:02d}-01"
    date_to = f"{year:04d}-{month:02d}-31" if month is not None else f"{year:04d}-12-31"
    parameters: list[object] = [date_from, date_to]

    with connect_database(paths) as conn:
        rows = conn.execute(
            """
            select
                categories.category_name,
                transactions.currency,
                count(*) as transaction_count,
                sum(-transactions.amount_minor_units) as spending_minor_units
            from transactions
            join categories using (category_id)
            where transactions.transaction_date >= ?
              and transactions.transaction_date <= ?
              and transactions.amount_minor_units < 0
              and transactions.transfer_status != 'confirmed'
            group by transactions.currency, categories.category_name
            order by transactions.currency, spending_minor_units desc, categories.category_name
            """,
            parameters,
        ).fetchall()

    return [
        SpendingReportRow(
            category_name=row["category_name"],
            currency=row["currency"],
            transaction_count=int(row["transaction_count"]),
            spending_minor_units=int(row["spending_minor_units"]),
        )
        for row in rows
    ]
```

- [x] **Step 4: Re-run focused tests and confirm they pass**

Run: `uv run pytest tests/test_reports.py -q`

Expected: all report query tests pass.

### Task 2: Report CLI

**Files:**
- Modify: `src/bankbuddy/cli.py`
- Test: `tests/test_report_cli.py`

- [x] **Step 1: Write failing CLI tests**

Create `tests/test_report_cli.py`:

```python
from click.testing import CliRunner

from bankbuddy.accounts import add_account
from bankbuddy.cli import main
from bankbuddy.imports import import_boa_csv
from bankbuddy.paths import resolve_app_paths


BOA_CSV = """Date,Description,Amount,Running Bal.
05/19/2026,GROCERY STORE,-42.17,100.00
06/10/2026,COFFEE SHOP,-4.25,95.75
06/11/2026,PAYROLL,2500.00,2595.75
"""


def seed_transactions(tmp_path):
    home = tmp_path / "home"
    paths = resolve_app_paths(home)
    account = add_account(
        paths,
        bank_name="Bank of America",
        country="US",
        account_number="123456789",
        account_type="checking",
        currency="USD",
    )
    csv_path = tmp_path / "boa.csv"
    csv_path.write_text(BOA_CSV, encoding="utf-8")
    import_boa_csv(paths, csv_path, account_id=account.account_id)
    return home


def test_report_spending_outputs_yearly_summary(tmp_path) -> None:
    home = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["report", "spending", "--year", "2026"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Category  Currency  Transactions  Spending" in result.output
    assert "Uncategorized  USD  2  46.42" in result.output


def test_report_spending_outputs_monthly_summary(tmp_path) -> None:
    home = seed_transactions(tmp_path)

    result = CliRunner().invoke(
        main,
        ["report", "spending", "--year", "2026", "--month", "6"],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Uncategorized  USD  1  4.25" in result.output
    assert "46.42" not in result.output


def test_report_spending_reports_empty_state(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["report", "spending", "--year", "2026"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "No spending found for 2026." in result.output
```

- [x] **Step 2: Run focused CLI tests and confirm they fail**

Run: `uv run pytest tests/test_report_cli.py -q`

Expected: Click reports no `report` command.

- [x] **Step 3: Implement the CLI group and spending subcommand**

Modify `src/bankbuddy/cli.py`:
- Import `spending_report`.
- Add `@main.group()` named `report`.
- Add `report spending --year YEAR [--month MONTH]`.
- Use `format_minor_units(row.spending_minor_units)` for display.
- Use Click ranges for year and month validation.
- Log count, year, and month through the runtime logger.

- [x] **Step 4: Re-run focused CLI tests and confirm they pass**

Run: `uv run pytest tests/test_report_cli.py -q`

Expected: all report CLI tests pass.

### Task 3: Docs And Validation

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`
- Modify: `docs/superpowers/plans/2026-06-12-spending-report.md`

- [x] **Step 1: Document report usage**

Add examples:

```bash
uv run bank-buddy report spending --year 2026
uv run bank-buddy report spending --year 2026 --month 5
```

Update the design spec changelog and Phase 1 roadmap to note the first spending report command.

- [x] **Step 2: Run final validation**

Run:

```bash
uv run pytest -q
./tests/validate.sh
git diff --check
```

Expected: all commands pass.

- [ ] **Step 3: Commit and open PR**

```bash
git add .
git commit -m "[codex] Add spending report command"
git push -u origin enhancement/29-20260612-spending-report
gh pr create --repo codeforester/bankbuddy --base main --head enhancement/29-20260612-spending-report --title "Add spending report command"
```
