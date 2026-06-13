# Bank Buddy — Design & Architecture Specification

**Version:** 1.12
**Status:** Draft
**Purpose:** Personal finance tracking tool for savvy users who want full
control of their financial data without relying on third-party services.

**Changelog:**
- v1.12: Added first-class BankBuddy environments. `BANKBUDDY_ENV`
  selects the named data environment, `BANKBUDDY_HOME` remains an explicit data
  home override, `status` reports both the environment and data home, and Base
  activation defaults development shells to the `dev` environment.
- v1.11: Added durable failed import attempts with account metadata and
  `import retry ATTEMPT_ID`, which retries a failed attempt by creating a new
  attempt from the recorded source path.
- v1.10: Added Bank of America PDF account auto-routing for `import inbox`
  when the statement account number matches exactly one configured account.
  CSV inbox imports still require `--account-id` because current BOA CSV files
  do not provide reliable account metadata.
- v1.9: Added the first managed inbox processing command,
  `import inbox --account-id`, for importing supported files from
  `~/BankBuddy/inbox` and removing successful inbox-owned source files after
  archival.
- v1.8: Added the SQLite export command with overwrite protection and a
  sensitive-data warning for database backups that include actual account
  numbers.
- v1.7: Added the first spending report command, `report spending`, with
  year and month filters and category/currency grouping for outgoing
  transactions.
- v1.6: Added canonical imported-statement filenames, import file archive
  metadata, and a managed `processed/<bank>/<year>/<month>/` copy for
  successful explicit imports while leaving source files untouched.
- v1.5: Added the first import attempt inspection command,
  `import history`, with status and limit filters so processed files and
  dedupe outcomes can be reviewed without opening SQLite directly.
- v1.4: Added the first transaction inspection command, `tx list`, with
  account-id and inclusive date-range filters so imported rows can be reviewed
  without opening SQLite directly.
- v1.3: Added the CLI runtime contract: Bank Buddy keeps Click as the command
  parser while following Base-style runtime conventions for debug logging,
  config loading, environment selection, temp preservation, log-file overrides,
  stdout/stderr separation, and safe diagnostics.
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
- Expose the CLI as a console script named `bankbuddy`.
- Follow Base-style CLI runtime behavior: root options for `--debug`,
  `--log-file`, `--keep-temp`, `--environment`, and `--config`; primary output
  on stdout; diagnostics on stderr; and no full account numbers or raw
  statement contents in logs.
- Use product-specific environment selection. `BANKBUDDY_ENV` selects the
  BankBuddy data environment for a shell session; `--environment` overrides it
  for one command; config `environment` is lower precedence; and `prod` is the
  default outside a project activation.
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

### Runtime Environments

BankBuddy environments are local data environments, not source checkouts.
`BANKBUDDY_HOME` points to the data home that contains the SQLite database and
managed directories such as `inbox`, `processed`, and `exports`.

Environment precedence:

1. `BANKBUDDY_HOME` overrides the data-home path.
2. `--environment <name>` selects the environment for one command.
3. `BANKBUDDY_ENV=<name>` selects the environment for a shell session.
4. Config `environment` is used when no command or session value is present.
5. `prod` is the default environment.

Default data-home mapping:

| Environment | Data home |
|---|---|
| `prod` | `~/BankBuddy` |
| `dev` | `~/BankBuddy-dev` |
| other names | `~/BankBuddy-<name>` |

Base activation for the source checkout exports `BANKBUDDY_ENV=dev` only when
the user has not already chosen an environment. It intentionally does not
export `BANKBUDDY_HOME`, so switching environments in the same shell remains a
simple `export BANKBUDDY_ENV=prod` or `export BANKBUDDY_ENV=dev`.

### Technology Stack

| Layer | Technology |
|---|---|
| Core language | Python 3.12+ |
| Project management | `uv` + `pyproject.toml` |
| CLI framework | `click` with Base-style runtime conventions |
| Database | SQLite |
| Migrations | Small SQL migration runner or lightweight Python migration layer |
| Phase 1 BOA PDF parsing | `pdfplumber` for text-selectable PDFs |
| Phase 1 CSV fallback parsing | Python `csv` module |
| Later spreadsheet parsing | `openpyxl` or `pandas` only when needed |
| Later PDF parsing | OCR or bank-specific PDF hardening after sample PDFs are validated |
| Categorization | Rule-based first, `scikit-learn` later |
| File watching | `watchdog` in a later automation phase |
| Web interface | Later, likely Node.js or Python depending on product needs |
| iOS app | Later, Swift/Xcode, local install only |

---

## 3. Supported Banks & Currencies

### Phase 1 Parser

- Bank of America (USA) — text-selectable PDF statement
- Bank of America (USA) — CSV export fallback when available

Phase 1 intentionally supports one bank first. The primary import path is a
text-selectable Bank of America PDF statement because CSV export may not be
available for every account flow. CSV remains supported when available, but OCR,
password-protected PDFs, and broad PDF layout support are later work.

### Later Banks

- HDFC Bank (India) — PDF statement, possibly password-protected
- ICICI Bank (India) — PDF statement, possibly password-protected

### Currencies

- Supported from the first implementation: USD and INR
- Future: Additional currencies can be added

Multi-currency support means the schema, import normalization, reports, and
budgets always carry a currency code. It does not mean every bank parser exists
in Phase 1. Bank of America PDF and CSV imports produce USD transactions first;
HDFC and ICICI add INR statement parsing in a later phase.

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
[ CLI: bankbuddy import ]
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
| `file_name` | TEXT NOT NULL | Last observed original filename |
| `file_hash` | TEXT NOT NULL UNIQUE | SHA-256 of file contents |
| `bank_id` | INTEGER FK | Nullable until inferred |
| `original_file_name` | TEXT | Original imported filename |
| `canonical_file_name` | TEXT | Parser-derived standard filename |
| `source_path` | TEXT | Absolute path of the explicit import source |
| `processed_path` | TEXT | Path relative to `~/BankBuddy/` for archived copy |
| `statement_start_date` | DATE | Inclusive statement period start |
| `statement_end_date` | DATE | Inclusive statement period end |
| `account_ref` | TEXT | Parser-confirmed account reference, usually last four |
| `source_format` | TEXT | Parser/source identifier such as `boa_pdf` |
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
| `account_id` | INTEGER FK | Nullable; selected or inferred account when known |
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
`file_hash` constraint. A retry creates a new `import_attempts` row and leaves
the original failed row intact.

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
|   `-- bank-of-america/
|       `-- 2026/
|           `-- 05/
|               `-- bank-of-america_1145_2026-04-23_2026-05-19.pdf
`-- exports/
```

Phase 1 imports an explicit `--file` path. Phase 2 adds `inbox/` scanning and
removes successfully imported inbox-owned source files after archival. Bank of
America PDFs can be auto-routed by full statement account number when it
matches exactly one configured BOA USD account. CSV inbox imports still require
an explicit account id until a supported CSV format provides reliable account
metadata. Automatic watching comes later.

### 6.2 Import Process

1. Import the explicit `--file` path, or scan visible files in `inbox/` with
   `import inbox`. Use `import inbox --account-id ACCOUNT_ID` when a supported
   format cannot infer the account safely, such as current BOA CSV files.
2. Compute SHA-256 hash of the file.
3. Detect file type.
4. Infer bank, account reference, and statement period from parser-specific
   signals.
5. Parse into staged transactions.
6. For PDF imports, validate that the full account number in the statement
   matches the selected configured account.
7. Copy the successfully recognized source file to the managed archive using
   the canonical filename and `processed/<bank-slug>/<year>/<month>/`
   hierarchy. Explicit source files are left untouched; successful inbox-owned
   source files are removed after the archive copy exists.
8. Create or update the `import_files` row with original filename, canonical
   filename, source path, processed path, account reference, source format, and
   statement period.
9. Start an `import_attempts` row for successful parser dispatch. If a
   supported file fails before commit, create a failed attempt with source path,
   source format, account id when known, and the error message.
10. Validate staged data:
   - required fields are present
   - dates are sensible
   - amounts parse into integer minor units
   - currency is known
   - duplicate-looking rows in the same batch are reported
11. Compute transaction hashes.
12. Skip existing transaction hashes and count them in the summary.
13. Apply deterministic category rules.
14. Commit new valid transactions in one database transaction.
15. Finish the import attempt with row counts and any warnings.

On failure before commit, no transaction rows are written and the file remains
in place. The failed attempt is recorded and can be retried. Retry reuses the
recorded source path when available, falls back to the managed processed copy
when present, and records the retry as a new attempt.

### 6.3 Import Summary Example

```text
File: boa_2025_11.pdf
Bank: Bank of America | Account ID: 1
Rows parsed:              87
Rows imported:            54
Duplicate rows skipped:   33
Warnings:                 0
```

### 6.4 Bank & Account Inference

Bank parsers own their inference rules because signals are bank-specific:

- known CSV headers
- known statement title/header patterns
- account number or last-four patterns; the BOA PDF parser strips spaces from
  the statement account number before matching it to `accounts.account_number`
- currency and date formats

If confidence is low, the command fails with a clear message. Later phases may
allow explicit overrides such as `--bank` or `--account` for formats that cannot
be inferred safely.

---

## 7. CLI Command Reference

Commands are implemented with `click` and exposed by `pyproject.toml` as
`bankbuddy`.

During development:

```bash
uv sync
uv run bankbuddy --help
uv run pytest
```

### Initialization

```text
bankbuddy init                         # Create local app directories and DB
bankbuddy status                       # Show DB path, tx count, date range
```

### Import Commands

```text
bankbuddy import inbox                 # Process routable files in inbox/
bankbuddy import inbox --account-id ID # Process files for an explicit account
bankbuddy import --file FILE           # Import a specific file
bankbuddy import history               # Show import history and results
bankbuddy import history --status STATUS --limit N
bankbuddy import retry ATTEMPT_ID      # Retry a failed import
bankbuddy import retry ATTEMPT_ID --account-id ID
```

### Transaction Commands

```text
bankbuddy tx list
bankbuddy tx list --account-id ACCOUNT_ID
bankbuddy tx list --from DATE --to DATE
bankbuddy tx categorize TX_ID CATEGORY
```

Later transaction commands and filters:

```text
bankbuddy tx list --bank BANK
bankbuddy tx list --category CATEGORY
bankbuddy tx list --uncategorized
```

### Reporting Commands

```text
bankbuddy report spending --year YEAR
bankbuddy report spending --year YEAR --month MONTH
bankbuddy report income --year YEAR
bankbuddy report trend --category CATEGORY
bankbuddy report budget --year YEAR
bankbuddy report budget --year YEAR --month MONTH
```

The first spending report counts outgoing transactions with
`amount_minor_units < 0`, excludes confirmed transfers, and groups by
transaction currency and category. This keeps Uncategorized imports visible
until category management exists.

### Category Commands

```text
bankbuddy category list
bankbuddy category add NAME --kind income|expense
bankbuddy category delete NAME
bankbuddy category rules list
bankbuddy category rules add PATTERN CATEGORY
bankbuddy category rules delete RULE_ID
```

### Budget Commands

```text
bankbuddy budget list
bankbuddy budget set CATEGORY CURRENCY TYPE MIN MAX
bankbuddy budget delete CATEGORY CURRENCY
```

### Setup & Admin Commands

```text
bankbuddy setup bank add
bankbuddy setup bank list
bankbuddy setup account add
bankbuddy setup account list
bankbuddy export sqlite --output FILE
bankbuddy export sqlite --output FILE --force
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
3. Manual training command, e.g. `bankbuddy category train`.
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
- `bankbuddy export sqlite --output FILE`
- schema migrations that are repeatable and testable
- import summaries that make skipped rows visible
- clear warning that local database/export files contain actual account numbers
- no destructive correction flows without confirmation

The SQLite export command refuses to overwrite an existing output file unless
`--force` is supplied, and it requires the output parent directory to already
exist.

Cloud sync and automated backup are out of scope for early phases.

---

## 13. Phased Roadmap

### Phase 0 — Project Skeleton and Tooling

- `pyproject.toml` with `uv` workflow
- `src/bankbuddy/` package layout
- `bankbuddy` console script
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
- `import history`
- `tx list`
- canonical import file names and managed archive copies for explicit imports
- `report spending`
- `export sqlite`
- local tests for parser, normalization, migrations, and CLI smoke paths

### Phase 2 — Broader Import Correctness

- inbox scanning with BOA PDF account auto-routing
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
