# Bank Buddy — Design & Architecture Specification

**Version:** 1.2
**Status:** Draft
**Purpose:** Personal finance tracking tool for savvy users who want full
control of their financial data without relying on third-party services.

**Changelog:**
- v1.2: Confirmed Python plus `uv`/`pyproject.toml` as the core project
  contract; made multi-currency data support part of the first implementation;
  narrowed Phase 1 parsing to a reliable Bank of America CSV vertical slice;
  revised money storage to integer minor units; confirmed that actual account
  numbers are stored in `accounts`; split file tracking from import attempts;
  moved PDF password handling, transfer matching, ML, LLM, web, and iOS work
  into later phases; added privacy and retry guardrails.
- v1.1: Added account type inference during import; added transaction-level
  deduplication via `transaction_hash`; updated import flow and bank/account
  inference strategy.

---

## 1. Vision & Goals

Bank Buddy is a locally installed, privacy-first personal finance tool. It lets
users consolidate bank statements from multiple banks and currencies, categorize
transactions intelligently, track spending trends, and manage budgets without
sharing bank credentials with a third party.

### Core Goals

- **Learning:** A meaningful Python project that covers CLI design, packaging,
  database design, statement parsing, testing, and later ML/UI development.
- **Personal optimization:** Make it easy to see where money is coming from and
  going, especially important post-salary life.
- **Privacy and security:** No bank credentials are stored. No cloud dependency
  is required. Data stays local by default.
- **Simplicity and durability:** Data remains available even if a third-party
  personal finance product shuts down.
- **Shareability:** Built for personal use first, then friends, then optionally
  wider distribution without App Store complexity.

### Target User

A digitally savvy user who knows how to log into a bank, download statement
files, and run CLI commands. This is not a general-public consumer app in the
early phases.

---

## 2. Language, Tooling, and Project Shape

Python is the best fit for the core implementation because Bank Buddy's hard
parts are statement parsing, CSV/PDF extraction, transaction normalization,
SQLite persistence, reporting queries, and a pleasant CLI. Python has mature
libraries for each of these, keeps iteration fast, and keeps the learning path
focused on the financial domain rather than infrastructure.

`uv` and `pyproject.toml` are the project contract from the first code commit.

### Phase 0 Project Contract

- Use `pyproject.toml` for package metadata, console scripts, dependency groups,
  lint/test configuration, and Python version constraints.
- Use `uv sync` to create the local environment and `uv run ...` for commands.
- Expose the CLI as a console script named `bank-buddy`.
- Treat currency as a first-class domain value from the first implementation:
  schema, parsing, formatting, reports, and budgets must carry ISO currency
  codes even when only one parser is implemented.
- Use a `src/` layout:

  ```text
  src/bankbuddy/
    migrations/
  tests/
  ```

- Keep parsing, normalization, persistence, and CLI modules separate so bank
  parsers can evolve independently.

### Technology Stack

| Layer | Technology |
|---|---|
| Core language | Python 3.12+ |
| Project management | `uv` + `pyproject.toml` |
| CLI framework | `click` |
| Database | SQLite |
| Migrations | Small SQL migration runner or lightweight Python migration layer |
| Phase 1 CSV parsing | Python `csv` module |
| Later spreadsheet parsing | `openpyxl` or `pandas` only when needed |
| Later PDF parsing | `pdfplumber` or `PyMuPDF` after sample PDFs are validated |
| Categorization | Rule-based first, `scikit-learn` later |
| File watching | `watchdog` in a later automation phase |
| Web interface | Later, likely Node.js or Python depending on product needs |
| iOS app | Later, Swift/Xcode, local install only |

---

## 3. Supported Banks & Currencies

### Phase 1 Parser

- Bank of America (USA) — CSV export only

Phase 1 intentionally supports one bank and one file format for parsing. The
first milestone should prove end-to-end correctness before broadening parser
support.

### Later Banks

- HDFC Bank (India) — PDF statement, possibly password-protected
- ICICI Bank (India) — PDF statement, possibly password-protected

### Currencies

- Supported from the first implementation: USD and INR
- Future: Additional currencies can be added

Multi-currency support means the schema, import normalization, reports, and
budgets always carry a currency code. It does not mean every bank parser exists
in Phase 1. Bank of America imports produce USD transactions first; HDFC and
ICICI add INR statement parsing in a later phase.

No cross-currency consolidation happens in early phases. Budgets and reports are
per-currency unless a later design explicitly adds conversion.

### Adding New Banks

New banks are supported by adding parser modules behind a shared parser
interface. Bank inference is automatic for supported formats. If the system
cannot identify the bank confidently, import fails loudly rather than guessing.

---

## 4. High-Level Architecture

```text
[ Bank Statement Files ]
        |
        v
[ Import Folder or --file Path ]
        |
        v
[ CLI: bank-buddy import ]
        |
        |-- Detect file type
        |-- Infer bank and account metadata
        |-- Record file + import attempt
        |-- Parse into staged transactions
        |-- Validate and normalize staged data
        |-- Deduplicate with visible summary
        |-- Categorize with deterministic rules
        |-- Commit valid new transactions
        |
        v
[ SQLite Database (local) ]
        |
        v
[ CLI: tx/report/budget/status/export ]
        |
        v
[ Later: automation, web dashboard, iOS viewer ]
```

The CLI is the primary interface until the database and import behavior are
boringly reliable. Web and iOS surfaces are consumers of the same local data
model, not separate products.

---

## 5. Data Model

All tables include `created_at` and `updated_at` columns. SQLite stores money as
integer minor units, never floating-point values.

### 5.1 `banks`

| Column | Type | Notes |
|---|---|---|
| `bank_id` | INTEGER PK | Surrogate key |
| `bank_name` | TEXT NOT NULL UNIQUE | e.g. "Bank of America" |
| `country` | TEXT NOT NULL | e.g. "US", "India" |
| `default_currency` | TEXT NOT NULL | ISO code, e.g. "USD" |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

PDF passwords do not belong in this table. Password handling is a later feature
that should use an interactive prompt first and macOS Keychain when persistence
is needed.

### 5.2 `accounts`

| Column | Type | Notes |
|---|---|---|
| `account_id` | INTEGER PK | Surrogate key |
| `bank_id` | INTEGER FK | References `banks.bank_id` |
| `account_number` | TEXT NOT NULL | Actual account number, not masked |
| `account_type` | TEXT NOT NULL | "checking", "savings", "cd", "credit_card", "investment" |
| `currency` | TEXT NOT NULL | ISO code |
| `statement_account_ref` | TEXT | Optional parser-visible reference such as masked number or last four |
| `display_name` | TEXT | Optional user-friendly account label |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

**Unique constraint:** `(bank_id, account_number)`.

Account type is inferred by the bank-specific parser when the statement has a
reliable signal. If account type cannot be inferred, the command should allow a
clear user override rather than silently guessing.

Bank Buddy stores the actual account number so account identity is unambiguous.
If a statement exposes only a masked number or last-four value, the import flow
must map that parser-visible value to a configured account rather than storing
the masked value as the account number.

### 5.3 `categories`

| Column | Type | Notes |
|---|---|---|
| `category_id` | INTEGER PK | Surrogate key |
| `category_name` | TEXT NOT NULL UNIQUE | |
| `category_kind` | TEXT NOT NULL | "income", "expense", or "special" |
| `is_system` | BOOLEAN NOT NULL | Built-in categories cannot be deleted |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

Built-in seed categories:

| Category | Kind |
|---|---|
| Salary | income |
| Interest | income |
| Dividends | income |
| Groceries | expense |
| Dining | expense |
| Utilities | expense |
| Travel | expense |
| Healthcare | expense |
| Shopping | expense |
| Entertainment | expense |
| Education | expense |
| Insurance | expense |
| Rent / Mortgage | expense |
| Transfer | special |
| Uncategorized | special |

### 5.4 `transactions`

| Column | Type | Notes |
|---|---|---|
| `transaction_id` | INTEGER PK | Surrogate key |
| `account_id` | INTEGER FK | References `accounts.account_id` |
| `category_id` | INTEGER FK | Defaults to Uncategorized |
| `file_id` | INTEGER FK | References `import_files.file_id` |
| `transaction_date` | DATE NOT NULL | |
| `amount_minor_units` | INTEGER NOT NULL | Positive = credit, negative = debit |
| `currency` | TEXT NOT NULL | ISO code |
| `description` | TEXT NOT NULL | Transaction remark from bank |
| `normalized_description` | TEXT NOT NULL | For matching and dedupe |
| `check_number` | TEXT | Optional |
| `source_row_key` | TEXT | Parser-provided row identity when available |
| `transaction_hash` | TEXT NOT NULL | Stable idempotency key |
| `transfer_pair_id` | TEXT | UUID for confirmed transfer pairs; nullable |
| `transfer_status` | TEXT NOT NULL | "none", "candidate", or "confirmed" |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

**Unique constraint:** `(account_id, transaction_hash)`.

`transaction_hash` should prefer parser-specific source row metadata when
available. A fallback hash may use account, date, amount, normalized
description, and source file context, but duplicate-looking rows should be
reported clearly. The user must be able to investigate skipped rows.

Only confirmed transfers are excluded from spending and income totals.
Transfer candidates remain visible until reviewed.

### 5.5 `import_files`

| Column | Type | Notes |
|---|---|---|
| `file_id` | INTEGER PK | Surrogate key |
| `file_name` | TEXT NOT NULL | Original filename |
| `file_hash` | TEXT NOT NULL UNIQUE | SHA-256 of file contents |
| `bank_id` | INTEGER FK | Nullable until inferred |
| `first_seen_at` | DATETIME NOT NULL | |
| `last_success_at` | DATETIME | Null until successful import |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

### 5.6 `import_attempts`

| Column | Type | Notes |
|---|---|---|
| `attempt_id` | INTEGER PK | Surrogate key |
| `file_id` | INTEGER FK | References `import_files.file_id` |
| `bank_id` | INTEGER FK | Nullable if inference failed |
| `import_status` | TEXT NOT NULL | "success", "failed", or "partial" |
| `started_at` | DATETIME NOT NULL | |
| `finished_at` | DATETIME | |
| `rows_parsed` | INTEGER NOT NULL DEFAULT 0 | |
| `rows_imported` | INTEGER NOT NULL DEFAULT 0 | |
| `rows_skipped_duplicate` | INTEGER NOT NULL DEFAULT 0 | |
| `transfer_candidates` | INTEGER NOT NULL DEFAULT 0 | |
| `error_message` | TEXT | Populated on failure |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

This split allows failed imports to be retried without fighting a unique
`file_hash` constraint.

### 5.7 `category_rules`

| Column | Type | Notes |
|---|---|---|
| `rule_id` | INTEGER PK | Surrogate key |
| `pattern` | TEXT NOT NULL | String or regex against normalized description |
| `category_id` | INTEGER FK | Target category |
| `priority` | INTEGER NOT NULL | Higher priority wins |
| `match_type` | TEXT NOT NULL | "contains" or "regex" |
| `is_user_defined` | BOOLEAN NOT NULL | True when created from user correction |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

When a user manually categorizes a transaction, Bank Buddy may propose a rule.
It should not blindly create an overly-specific rule from the full transaction
description if that would be noisy.

### 5.8 `budgets`

| Column | Type | Notes |
|---|---|---|
| `budget_id` | INTEGER PK | Surrogate key |
| `category_id` | INTEGER FK | References `categories.category_id` |
| `currency` | TEXT NOT NULL | ISO code |
| `budget_type` | TEXT NOT NULL | "monthly" or "annual" |
| `min_amount_minor_units` | INTEGER | Optional lower bound |
| `max_amount_minor_units` | INTEGER | Optional upper bound |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

**Unique constraint:** `(category_id, currency)`.

A category can have either a monthly or annual budget per currency. Switching
types updates the existing budget record.

---

## 6. Import Flow

### 6.1 Local Folder Structure

```text
~/BankBuddy/
|-- inbox/
|-- processed/
|   |-- Bank of America/
|   |-- HDFC Bank/
|   `-- ICICI Bank/
`-- exports/
```

Phase 1 imports an explicit `--file` path. Phase 2 adds `inbox/` scanning and
processed-file movement. Automatic watching comes later.

### 6.2 Import Process

1. Import the explicit `--file` path. Later phases may scan `inbox/`.
2. Compute SHA-256 hash of the file.
3. Create or update the `import_files` row.
4. If the file already has a successful import, skip by default and report it.
5. Start an `import_attempts` row.
6. Detect file type.
7. Infer bank and account metadata from parser-specific signals.
8. Parse into staged transactions.
9. Validate staged data:
   - required fields are present
   - dates are sensible
   - amounts parse into integer minor units
   - currency is known
   - duplicate-looking rows in the same batch are reported
10. Compute transaction hashes.
11. Skip existing transaction hashes and count them in the summary.
12. Apply deterministic category rules.
13. Commit new valid transactions in one database transaction.
14. For the later inbox workflow, move successfully imported files to
    `processed/<Bank Name>/`.
15. Finish the import attempt with row counts and any warnings.

On failure before commit, no transaction rows are written and the file remains
in place. The failed attempt is recorded and can be retried.

### 6.3 Import Summary Example

```text
File: boa_2025_11.csv
Bank: Bank of America | Account type: checking
Rows parsed:              87
Rows imported:            54
Duplicate rows skipped:   33
Warnings:                 0
```

### 6.4 Bank & Account Inference

Bank parsers own their inference rules because signals are bank-specific:

- known CSV headers
- known statement title/header patterns
- account number or last-four patterns
- currency and date formats

If confidence is low, the command fails with a clear message. Later phases may
allow explicit overrides such as `--bank` or `--account` for formats that cannot
be inferred safely.

---

## 7. CLI Command Reference

Commands are implemented with `click` and exposed by `pyproject.toml` as
`bank-buddy`.

During development:

```bash
uv sync
uv run bank-buddy --help
uv run pytest
```

### Initialization

```text
bank-buddy init                         # Create local app directories and DB
bank-buddy status                       # Show DB path, tx count, date range
```

### Import Commands

```text
bank-buddy import                       # Process inbox/ in Phase 2+
bank-buddy import --file FILE           # Import a specific file
bank-buddy import --status              # Show import history and results
bank-buddy import --retry ATTEMPT_ID    # Retry a failed import
```

### Transaction Commands

```text
bank-buddy tx list
bank-buddy tx list --bank BANK
bank-buddy tx list --from DATE --to DATE
bank-buddy tx list --category CATEGORY
bank-buddy tx list --uncategorized
bank-buddy tx categorize TX_ID CATEGORY
```

### Reporting Commands

```text
bank-buddy report spending --year YEAR
bank-buddy report spending --year YEAR --month MONTH
bank-buddy report income --year YEAR
bank-buddy report trend --category CATEGORY
bank-buddy report budget --year YEAR
bank-buddy report budget --year YEAR --month MONTH
```

### Category Commands

```text
bank-buddy category list
bank-buddy category add NAME --kind income|expense
bank-buddy category delete NAME
bank-buddy category rules list
bank-buddy category rules add PATTERN CATEGORY
bank-buddy category rules delete RULE_ID
```

### Budget Commands

```text
bank-buddy budget list
bank-buddy budget set CATEGORY CURRENCY TYPE MIN MAX
bank-buddy budget delete CATEGORY CURRENCY
```

### Setup & Admin Commands

```text
bank-buddy setup bank add
bank-buddy setup bank list
bank-buddy setup account add
bank-buddy setup account list
bank-buddy export sqlite --output FILE
```

Password commands should prompt interactively. Passwords should not be passed as
plain CLI arguments.

---

## 8. Categorization Engine

### Deterministic Rules

- Phase 1 assigns transactions to Uncategorized unless a built-in rule exists.
- Later rule-management work matches normalized descriptions by priority.
- Manual categorization updates the selected transaction.
- User corrections may create or suggest category rules once rule management is
  implemented.

### Later: ML-Assisted Categorization

After enough manually categorized transactions exist, Bank Buddy can add a local
classifier:

1. TF-IDF vectorization of normalized transaction descriptions.
2. Naive Bayes or Logistic Regression classifier.
3. Manual training command, e.g. `bank-buddy category train`.
4. Local model file under the Bank Buddy app directory.
5. Confidence threshold that falls back to Uncategorized.

### Later: Optional LLM Fallback

LLM categorization conflicts with the strict local-first privacy story unless it
is explicit and opt-in. If added, it must:

- be disabled by default
- warn that transaction descriptions leave the machine
- avoid sending account numbers or balances
- allow local-only operation forever

---

## 9. Transfer Handling

Automatic transfer matching is useful but easy to get wrong. The first
implementation should treat matches as candidates rather than silently changing
financial reports.

Candidate signal:

- same absolute amount
- opposite signs
- known accounts
- dates within a configurable window, initially two days

Confirmed transfers receive the Transfer category and a shared
`transfer_pair_id`. Only confirmed transfers are excluded from income, spending,
and budget calculations.

---

## 10. Budget Analysis

- Budget calculations are on-the-fly; no aggregate tables are stored in early
  phases.
- Monthly budgets compare category totals within one calendar month.
- Annual budgets compare category totals within one calendar year.
- Transfers are excluded only when confirmed.
- Budgets are per-currency.
- Money comparisons use integer minor units.

---

## 11. Password-Protected PDFs

PDF support starts after the CSV import contract is proven.

Password handling rules:

- Do not pass passwords as CLI arguments.
- Prompt interactively when a password is needed.
- Prefer macOS Keychain for stored passwords.
- If Keychain support is deferred, do not persist passwords.
- Allow explicit bank/account hints for encrypted files when content cannot be
  inspected before decryption.

Plaintext password storage in SQLite is not acceptable for the shareable
version of the tool.

---

## 12. Backup, Export, and Durability

Because this is personal finance data, durability is a first-class requirement.

Early implementation should include:

- clear database location
- `bank-buddy export sqlite --output FILE`
- schema migrations that are repeatable and testable
- import summaries that make skipped rows visible
- clear warning that local database/export files contain actual account numbers
- no destructive correction flows without confirmation

Cloud sync and automated backup are out of scope for early phases.

---

## 13. Phased Roadmap

### Phase 0 — Project Skeleton and Tooling

- `pyproject.toml` with `uv` workflow
- `src/bankbuddy/` package layout
- `bank-buddy` console script
- test runner and baseline CI
- SQLite connection and migration skeleton
- app directory discovery
- currency helpers for USD and INR parsing/formatting

### Phase 1 — Bank of America CSV Vertical Slice

- SQLite schema for banks, accounts, categories, transactions, import files,
  and import attempts
- seed categories
- Bank of America CSV parser
- import explicit CSV file
- USD and INR schema support, with the first parser producing USD transactions
- transaction hash deduplication with visible summary
- `tx list`
- basic spending report
- SQLite export command
- local tests for parser, normalization, migrations, and CLI smoke paths

### Phase 2 — Broader Import Correctness

- inbox scanning and processed-file movement
- account setup/list commands
- retry failed imports
- HDFC and ICICI PDF parser spikes using real samples
- interactive PDF password prompt
- INR import path through Indian bank parsers
- transfer candidate detection

### Phase 3 — Categorization and Budgets

- category rule management
- manual transaction categorization
- suggested rules from corrections
- budget CRUD
- monthly and annual budget reports
- confirmed transfer review flow

### Phase 4 — Intelligence and Automation

- local ML categorization with `scikit-learn`
- optional LLM fallback with explicit privacy warning
- `watchdog` inbox automation
- macOS `launchd` integration
- local notifications on import completion

### Phase 5 — Interfaces

- read-only web dashboard
- charts for spending, income, and budgets
- later web recategorization/budget management
- local iOS viewer via Xcode-installed app

---

## 14. Design Principles

- **Correctness before breadth.** One reliable parser is better than three
  fragile ones.
- **Fail loudly, not silently.** Ambiguous bank, account, amount, or date data
  should stop the import or become an explicit review item.
- **Never pollute the transaction table.** Parse and validate before commit.
- **Money is integer data.** Store minor units, never floats.
- **Retries are normal.** Failed imports should be visible and retryable.
- **Local first.** Cloud, LLM, and sync features are opt-in later layers.
- **Extensible without ceremony.** Parser modules should be easy to add, but the
  first implementation should stay small.

---

## 15. Out of Scope for Phase 1

- PDF import
- HDFC and ICICI support
- Password storage
- Automatic bank connectivity such as Plaid or Open Banking APIs
- Cross-currency consolidation
- Transfer auto-confirmation
- ML or LLM categorization
- File watching or background daemon
- Web or iOS interfaces
- Cloud sync or backup
- App Store distribution

---

*Document generated from design discussion and review. Ready for Phase 0
implementation planning.*
