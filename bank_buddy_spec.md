# Bank Buddy — Design & Architecture Specification

**Version:** 1.34
**Status:** Draft
**Purpose:** Personal finance tracking tool for savvy users who want full
control of their financial data without relying on third-party services.

**Changelog:**
- v1.34: Added the first TaxBuddy implementation slice: `taxbuddy` console
  script, `tax_documents` index, explicit-file and inbox imports, dry-run
  planning, SHA-256 idempotency, canonical `tax/processed/...` archival, and
  `docs list/show`.
- v1.33: Added the canonical data-home layout with
  `database/bankbuddy.sqlite3`, banking files under `bank/`, tax files under
  `tax/`, legacy layout detection, and `storage migrate-layout` for safe
  dry-run-first migration.
- v1.32: Documented the planned TaxBuddy layer as a second `taxbuddy`
  CLI in the same repo and SQLite database. TaxBuddy is scoped to tax
  document indexing, expected-form gap detection, and annual readiness
  summaries, not tax filing or liability calculation.
- v1.31: Added `bank list`, `bank rename`, and
  `account update --display-name` for correcting configured bank and account
  display labels without changing stored actual account numbers.
- v1.30: Added Apple Card text-PDF imports with content-based PDF detection,
  product-ref account routing, credit-card sign normalization, zero-activity
  statement archival, and latest balance snapshots.
- v1.29: Added concrete `account ref add --help` examples for product,
  last-four, and full-account-number statement reference mappings.
- v1.28: Made `account list` use the standard pretty-table renderer and added
  `account show --show-full-account-number` as an explicit opt-in reveal for
  one stored account number.
- v1.27: Added first-class `account_statement_refs` for parser-visible
  account identifiers, plus `account ref` CLI management. Import routing is
  based on content extracted from files, not source filenames, and explicit
  `--account-id` fails when document identity maps to a different account.
- v1.26: Added `audit statements --bank` so statement coverage audits can be
  narrowed by bank name consistently with statement inventory and transaction
  listing commands.
- v1.25: Added HDFC Bank `.xls` statement import with INR transactions,
  statement-period metadata, value dates, row-balance sanity checks, inbox
  account auto-routing, account latest balance snapshots, and boundary-row
  deduplication across adjacent statement exports.
- v1.24: Added `Rental Income` as a built-in system income category, with a
  migration that backfills existing databases.
- v1.23: Added the manual categorization MVP: `category list`,
  `tx categorize TX_ID CATEGORY`, `tx list --category`, and
  `tx list --uncategorized`. Transaction default and ledger views now include
  the assigned category while compact view remains narrow.
- v1.22: Added ICICI Bank `.xls` statement import as the first INR bank parser.
  ICICI imports use the spreadsheet account number for validation/routing, store
  transaction value dates, use row balances for sanity checks, and update an
  account-level latest balance snapshot with source file provenance. Full
  statement/transaction balance history remains future work.
- v1.21: Added `statements summary` and `statements list` for read-only
  imported statement-file inventory by bank, account, year, and month. The
  inventory view is separate from coverage auditing and uses successful import
  metadata.
- v1.20: Added `audit statements` for read-only imported statement coverage
  checks. The audit supports `--years`, explicit `--from/--to` date ranges,
  `--bank`, `--account-id`, and `--account-last4`, and reports missing gaps,
  overlaps, duplicate periods, and covered periods.
- v1.19: Added `tx list --bank`, `--currency`, `--account-number`, and
  `--account-last4` filters. Full account numbers may be used to filter rows,
  but list output remains display-name or masked-suffix based.
- v1.18: Added `tx list --format pretty|csv|tsv`, made aligned `pretty`
  output the default, and kept CSV/TSV transaction output to clean rectangular
  rows without JSON or YAML.
- v1.17: Added `tx list --sort`, `--order`, `--view`, and `--summary` so
  transaction review can order rows, switch human-readable layouts, and print
  per-currency totals for the filtered result set.
- v1.16: Added `tx list --direction debit|credit` so transaction review can
  focus on outgoing negative amounts or incoming positive amounts.
- v1.15: Extended Bank of America PDF statement-period extraction to support
  account header lines that use `for <date> to <date> Account number`, matching
  real eStatement text extraction.
- v1.14: Added `import --dry-run` for explicit files and inbox processing.
  Dry-run mode parses, validates, plans canonical archive paths, reports
  transaction and exact-file duplicates, and leaves the database and filesystem
  unchanged.
- v1.13: Added exact duplicate inbox handling. Files with a SHA-256 hash that
  matches a prior successful import are skipped before parser work, recorded as
  `duplicate` attempts, and temporarily preserved under `bank/duplicates/`.
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
  `~/BankBuddy/bank/inbox` and removing successful inbox-owned source files after
  archival.
- v1.8: Added the SQLite export command with overwrite protection and a
  sensitive-data warning for database backups that include actual account
  numbers.
- v1.7: Added the first spending report command, `report spending`, with
  year and month filters and category/currency grouping for outgoing
  transactions.
- v1.6: Added canonical imported-statement filenames, import file archive
  metadata, and a managed `bank/processed/<bank>/<year>/<month>/` copy for
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
sharing bank credentials with a third party. The planned TaxBuddy layer extends
the same document-centric model to tax document readiness: what documents have
arrived, what forms are expected, and what gaps need attention before tax
season.

### Core Goals

- **Learning:** A meaningful Python project that covers CLI design, packaging,
  database design, statement parsing, testing, and later ML/UI development.
- **Personal optimization:** Make it easy to see where money is coming from and
  going, especially important post-salary life.
- **Privacy and security:** No bank credentials are stored. No cloud dependency
  is required. Data stays local by default.
- **Simplicity and durability:** Data remains available even if a third-party
  personal finance product shuts down.
- **Tax readiness:** Organize tax documents and surface missing expected forms
  without pretending to prepare or file tax returns.
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
- Expose the banking CLI as a console script named `bankbuddy`. Tax document
  workflows later expose a second console script named `taxbuddy` from the same
  repo and package.
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
    tax/                  # planned TaxBuddy modules
    migrations/
  tests/
  ```

- Keep parsing, normalization, persistence, and CLI modules separate so bank
  parsers can evolve independently.

### Runtime Environments

BankBuddy environments are local data environments, not source checkouts.
`BANKBUDDY_HOME` points to the data home that contains the SQLite database and
managed directories. New homes use `database/bankbuddy.sqlite3`, bank statement
folders under `bank/`, and tax document folders under `tax/`.

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
| Text PDF parsing | `pdfplumber` for supported text-selectable PDF statements |
| Phase 1 CSV fallback parsing | Python `csv` module |
| Indian bank old Excel parsing | `xlrd` for ICICI and HDFC `.xls` statement exports |
| Later `.xlsx` spreadsheet parsing | `openpyxl` or `pandas` only when needed |
| Later PDF parsing | OCR or bank-specific PDF hardening after sample PDFs are validated |
| Categorization | Rule-based first, `scikit-learn` later |
| File watching | `watchdog` in a later automation phase |
| Web interface | Later, likely Node.js or Python depending on product needs |
| iOS app | Later, Swift/Xcode, local install only |

---

## 3. Supported Banks & Currencies

### Current Parsers

- Bank of America (USA) — text-selectable PDF statement
- Bank of America (USA) — CSV export fallback when available
- Apple Card / Goldman Sachs (USA) — text-selectable PDF statement
- ICICI Bank (India) — old Excel `.xls` statement export
- HDFC Bank (India) — old Excel `.xls` statement export

The first implementation intentionally started with one bank. The Bank of
America primary import path is a text-selectable PDF statement because CSV
export may not be available for every account flow. CSV remains supported when
available, but OCR, password-protected PDFs, and broad PDF layout support are
later work.
Apple Card PDF support covers text-selectable statements whose content
identifies Apple Card and Goldman Sachs Bank USA. These statements do not expose
a stable account number, so they route through configured product refs such as
`Apple Card`.
ICICI and HDFC `.xls` support covers the first INR parser family because these
spreadsheets contain reliable table columns, full account metadata, value
dates, transaction dates, withdrawal/deposit amounts, and running balances.
ICICI and HDFC PDFs remain archival reference input until separate parsers are
justified.

### Later Banks

- HDFC Bank (India) — PDF statement for earlier years, possibly password-protected
- ICICI Bank (India) — PDF statement, possibly password-protected

### Currencies

- Supported from the first implementation: USD and INR
- Future: Additional currencies can be added

Multi-currency support means the schema, import normalization, reports, and
budgets always carry a currency code. Bank of America PDF and CSV imports
produce USD transactions. Apple Card PDF imports produce USD credit-card
transactions. ICICI `.xls` imports produce INR transactions. HDFC `.xls`
imports produce INR transactions. Other Indian bank parsers remain later work.

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
| `country` | TEXT NOT NULL | ISO 3166-1 alpha-2 code, e.g. "US", "IN" |
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
| `statement_account_ref` | TEXT | Advanced parser-visible alias for statement formats that expose only a masked account reference |
| `display_name` | TEXT | Optional user-friendly account label |
| `latest_balance_minor_units` | INTEGER | Latest statement-derived account balance snapshot |
| `latest_balance_currency` | TEXT | ISO code for the latest balance |
| `latest_balance_as_of_date` | DATE | Statement date the latest balance is good as of |
| `latest_balance_source_file_id` | INTEGER FK | Import file that supplied the latest balance |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

**Unique constraint:** `(bank_id, account_number)`.

Account type is inferred by the bank-specific parser when the statement has a
reliable signal. If account type cannot be inferred, the command should allow a
clear user override rather than silently guessing.

Bank Buddy stores the actual account number so account identity is unambiguous.
Country values are stored as normalized ISO 3166-1 alpha-2 codes such as `US`
and `IN`; the CLI may accept friendly aliases such as `USA` or `India`, but it
must normalize before persistence. If a statement exposes only a masked number
or last-four value, the import flow must map that parser-visible value to a
configured account rather than storing the masked value as the account number.

The latest balance fields are a convenience snapshot, not a complete balance
history and not a live bank balance. They are updated only from successful
imports whose statement balance date is at least as current as the stored
snapshot. Historical `statement_balances` or per-row `transaction_balances`
belong to the separate balance-history design.

### 5.2.1 `account_statement_refs`

`account_statement_refs` stores parser-visible account identifiers that are not
the canonical account number. Examples include last-four values, masked account
references, or product identifiers for statements that expose only a bank or
product identity.

| Column | Type | Notes |
|---|---|---|
| `account_statement_ref_id` | INTEGER PK | Surrogate key |
| `account_id` | INTEGER FK | References `accounts.account_id` |
| `source_format` | TEXT NOT NULL | Parser format such as `boa_pdf`, or `*` for any |
| `ref_type` | TEXT NOT NULL | `full_account_number`, `last4`, `masked_account`, or `product` |
| `ref_value` | TEXT NOT NULL | Original configured value |
| `normalized_ref_value` | TEXT NOT NULL | Matching value normalized by ref type |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

The import resolver combines parser-detected bank, currency, account-number
signals, and `account_statement_refs`. A statement may auto-route only when
the extracted content maps to exactly one configured account. If the user
passes `--account-id` and the document identity maps to another account, the
import fails cleanly.

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
| Rental Income | income |
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
| `value_date` | DATE | Optional bank-provided value date |
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
| `processed_path` | TEXT | Path relative to the data home for archived copy, such as `bank/processed/...` |
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
| `import_status` | TEXT NOT NULL | "success", "failed", "partial", or "duplicate" |
| `started_at` | DATETIME NOT NULL | |
| `finished_at` | DATETIME | |
| `rows_parsed` | INTEGER NOT NULL DEFAULT 0 | |
| `rows_imported` | INTEGER NOT NULL DEFAULT 0 | |
| `rows_skipped_duplicate` | INTEGER NOT NULL DEFAULT 0 | |
| `transfer_candidates` | INTEGER NOT NULL DEFAULT 0 | |
| `error_message` | TEXT | Populated on failure |
| `duplicate_path` | TEXT | Duplicate archive path for exact duplicate attempts |
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
|-- database/
|   `-- bankbuddy.sqlite3
|-- bank/
|   |-- inbox/
|   |-- processed/
|   |   `-- bank-of-america/
|   |       `-- 2026/
|   |           `-- 05/
|   |               `-- bank-of-america_1145_2026-04-23_2026-05-19.pdf
|   |-- duplicates/
|   |   `-- bank-of-america/
|   |       `-- 2026/
|   |           `-- 05/
|   |               `-- bank-of-america_1145_2026-04-23_2026-05-19.pdf
|   `-- exports/
`-- tax/
    |-- inbox/
    |-- processed/
    |-- duplicates/
    `-- exports/
```

BankBuddy should detect old data homes that still have root-level
`bankbuddy.sqlite3`, `inbox/`, `processed/`, `duplicates/`, or `exports/`, then
operate in legacy mode until the user runs `storage migrate-layout`. Migration
must be dry-run-first, refuse overwrite scenarios, move the database to
`database/bankbuddy.sqlite3`, move banking folders under `bank/`, and update
stored `processed_path` and `duplicate_path` values. Historical `source_path`
values remain unchanged because they describe where the user originally
imported a file from.

Phase 1 imports an explicit `--file` path. Phase 2 adds `bank/inbox/` scanning and
removes successfully imported inbox-owned source files after archival. Exact
duplicates of prior successful imports are detected by SHA-256 hash before
parser work, recorded as `duplicate` attempts, and moved to `bank/duplicates/`
as a temporary conservative preservation policy. Import routing must be based
on content extracted from the file, never the source filename. Bank of America
PDFs, Apple Card PDFs, ICICI `.xls` files, and HDFC `.xls` files can be
auto-routed by parser-detected account identity when it maps to exactly one
configured account. `account_statement_refs` extends that identity model to
statement formats that expose only last-four, masked, or product-level
identifiers. CSV inbox imports still require an explicit account id until a
supported CSV format provides reliable account metadata, except when the CSV
file is an exact duplicate of a prior successful import. Automatic watching
comes later.

All explicit-file and inbox imports can run with `--dry-run`. Dry-run mode
uses the same parser, account validation, transaction hashing, duplicate
detection, and canonical archive path planning as a real import, but it does
not write transactions, import files, import attempts, duplicate attempts,
processed files, duplicate files, or remove inbox files.

### 6.2 Import Process

1. Import the explicit `--file` path, or scan visible files in `bank/inbox/` with
   `import inbox`. Use `import inbox --account-id ACCOUNT_ID` when a supported
   format cannot infer the account safely, such as current BOA CSV files. Add
   `--dry-run` to either mode to preview the plan without durable changes.
2. Compute SHA-256 hash of the file.
3. For inbox imports, if the hash matches an `import_files` row with
   `last_success_at`, skip parser work, preserve the source file under
   `bank/duplicates/<bank-slug>/<year>/<month>/`, record a `duplicate` attempt with
   `duplicate_path`, and remove the file from `bank/inbox/`. In dry-run mode,
   report the planned duplicate path but do not copy, record, or remove the file.
4. Detect file type.
5. Infer bank, account reference, and statement period from parser-specific
   signals. PDF imports first detect the statement format from document
   content. Bank of America PDFs support both `Statement Period: ... through
   ...` headers and account header lines shaped like `for ... to ... Account
   number`. Apple Card PDFs use the Apple Card / Goldman Sachs content
   signature, statement period, total balance, payment rows, purchase/credit
   rows, and product refs. ICICI `.xls` imports use spreadsheet account,
   statement period, value date, transaction date, withdrawal/deposit, and
   balance columns. HDFC `.xls` imports use the analogous HDFC columns and skip
   masked separator and statement-summary rows.
6. Parse into staged transactions.
7. Resolve the parsed statement identity to a configured account. If
   `--account-id` was supplied, treat it as an assertion: when the document
   exposes an account identity that maps to a different account, fail cleanly.
8. Copy the successfully recognized source file to the managed archive using
   the canonical filename and `bank/processed/<bank-slug>/<year>/<month>/`
   hierarchy. Explicit source files are left untouched; successful inbox-owned
   source files are removed after the archive copy exists.
9. Create or update the `import_files` row with original filename, canonical
   filename, source path, processed path, account reference, source format, and
   statement period.
10. Start an `import_attempts` row for successful parser dispatch. If a
   supported file fails before commit, create a failed attempt with source path,
   source format, account id when known, and the error message.
11. Validate staged data:
   - required fields are present
   - dates are sensible
   - amounts parse into integer minor units
   - currency is known
   - duplicate-looking rows in the same batch are reported
12. Compute transaction hashes.
13. Skip existing transaction hashes and count them in the summary.
14. Apply deterministic category rules.
15. Commit new valid transactions in one database transaction.
16. When the parser exposes a statement closing balance, update the account's
    latest-balance snapshot with balance amount, currency, as-of date, and
    source file id if the statement is at least as current as the stored
    snapshot.
17. Finish the import attempt with row counts and any warnings.

On failure before commit, no transaction rows are written and the file remains
in place. The failed attempt is recorded and can be retried. Retry reuses the
recorded source path when available, falls back to the managed processed copy
when present, and records the retry as a new attempt.

In dry-run mode, supported failures are reported but not recorded in
`import_attempts`, because dry-run is intentionally read-only.

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

Bank parsers own their extraction rules because signals are bank-specific:

- known CSV headers
- known statement title/header patterns
- account number or last-four patterns; the BOA PDF parser strips spaces from
  the statement account number before matching it to `accounts.account_number`
- currency and date formats

The generic resolver owns account matching after parser extraction. It combines
bank, currency, full account numbers, and configured `account_statement_refs`.
If confidence is low or multiple accounts match, the command fails with a clear
message. Later phases may allow explicit overrides such as `--bank` or
`--account` for formats that cannot be inferred safely.

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
bankbuddy storage migrate-layout --dry-run
                                        # Preview legacy-to-canonical storage move
bankbuddy storage migrate-layout --apply
                                        # Move legacy storage after reviewing plan
```

### Import Commands

```text
bankbuddy import inbox                 # Process routable files in inbox/
bankbuddy import inbox --account-id ID # Process files for an explicit account
bankbuddy import --dry-run inbox       # Preview inbox processing
bankbuddy import --file FILE --account-id ID
bankbuddy import --dry-run --file FILE --account-id ID
bankbuddy import history               # Show import history and results
bankbuddy import history --status STATUS --limit N
bankbuddy import retry ATTEMPT_ID      # Retry a failed import
bankbuddy import retry ATTEMPT_ID --account-id ID
```

### Transaction Commands

```text
bankbuddy tx list
bankbuddy tx list --account-id ACCOUNT_ID
bankbuddy tx list --bank BANK
bankbuddy tx list --currency CURRENCY
bankbuddy tx list --account-number ACCOUNT_NUMBER
bankbuddy tx list --account-last4 LAST4
bankbuddy tx list --from DATE --to DATE
bankbuddy tx list --direction debit
bankbuddy tx list --direction credit
bankbuddy tx list --sort FIELD[:asc|desc],FIELD[:asc|desc]
bankbuddy tx list --sort FIELD --order asc|desc
bankbuddy tx list --view default|compact|ledger
bankbuddy tx list --format pretty|csv|tsv
bankbuddy tx list --summary
bankbuddy tx list --category CATEGORY
bankbuddy tx list --uncategorized
bankbuddy tx categorize TX_ID CATEGORY
```

`tx list --direction debit` shows negative-amount transactions. `tx list
--direction credit` shows positive-amount transactions. The direction filter
can be combined with account, bank, currency, and date filters.

`tx list --bank` matches the configured bank name case-insensitively.
`tx list --currency` filters by normalized ISO currency code. `tx list
--account-number` accepts the actual stored account number after digit
normalization and returns no rows if no configured account matches. `tx list
--account-last4` is a convenience selector that must resolve to exactly one
configured account; missing or ambiguous suffixes fail with a clear error so
the user can switch to `--account-id` or `--account-number`. Transaction list
output still uses display names or masked account suffixes and never prints the
full account number.

All transaction-list filters compose with each other. For example, a user can
combine `--bank`, `--currency`, `--account-last4`, `--direction`, date range,
category, sort, view, format, and summary flags in one command. `--category`
matches an existing category name case-insensitively. `--uncategorized` selects
transactions still assigned to the built-in Uncategorized category. `--category`
and `--uncategorized` are mutually exclusive.

`tx list --sort` accepts comma-separated public fields: `id`, `date`, `amount`,
`account`, `currency`, and `description`. Field-level directions such as
`amount:desc` override the global `--order`; otherwise `--order` applies to
fields without an explicit direction. The default order remains
`date:asc,id:asc` when no sort expression is provided.

`tx list --view default` keeps the standard transaction table with category,
`--view compact` shows a narrower date/amount/currency/description table, and
`--view ledger` adds a debit/credit type column while also showing category.
`tx list --summary` prints transaction count, debits, credits, and net totals
grouped by currency for the same filtered rows.

`tx list --format pretty` is the default and renders aligned columns for human
reading. `--format csv` and `--format tsv` use the selected `--view` columns
with lowercase stable headers for machine-readable output. `--summary` is only
supported with `--format pretty`; CSV and TSV intentionally remain one clean
transaction table. JSON and YAML are out of scope for transaction listing.

### Statement Inventory Commands

```text
bankbuddy statements summary
bankbuddy statements summary --by year
bankbuddy statements summary --by month
bankbuddy statements summary --years YEAR[,YEAR...]
bankbuddy statements summary --bank BANK_NAME
bankbuddy statements summary --account-id ACCOUNT_ID
bankbuddy statements summary --account-last4 LAST4
bankbuddy statements list
bankbuddy statements list --year YEAR
bankbuddy statements list --bank BANK_NAME
bankbuddy statements list --account-id ACCOUNT_ID
bankbuddy statements list --account-last4 LAST4
```

`statements summary` and `statements list` are read-only inventory views over
successful statement imports. `summary` groups statement files by statement end
year by default, or by statement end month with `--by month`. `list` shows one
row per successfully imported statement file, ordered by bank, account, and
statement period.

The inventory uses the first successful import attempt for each file/account
pair as the representative row, so repeated explicit imports do not inflate
file counts. Exact duplicate inbox attempts remain operational import history
and are not counted as imported statement files. The command can be filtered by
bank name, account id, unambiguous account last four digits, and statement end
year.

### Audit Commands

```text
bankbuddy audit statements
bankbuddy audit statements --years YEAR[,YEAR...]
bankbuddy audit statements --from DATE --to DATE
bankbuddy audit statements --bank BANK_NAME
bankbuddy audit statements --account-id ACCOUNT_ID
bankbuddy audit statements --account-last4 LAST4
```

`audit statements` checks imported statement metadata and does not mutate
database rows or statement files. It uses successful import attempts with a
configured account and statement start/end dates. The first version reports
`covered`, `missing`, `overlap`, and `duplicate` periods in human-readable
pretty tables.

`--years` and `--from/--to` are mutually exclusive. `--years 2024,2025`
audits each requested calendar year as an independent window. `--from` and
`--to` define one continuous inclusive date range and must be provided
together. If no date selector is provided, the audit uses each selected
account's imported coverage range.

The account selectors are `--bank`, `--account-id`, and `--account-last4`.
`--bank` matches the configured bank name case-insensitively.
`--account-last4` must resolve to exactly one configured account, after any
bank filter is applied. Balance
reconciliation and missing-transaction inference beyond parser-local row
balance checks are out of scope until statement balance history is designed and
stored. The account-level latest balance snapshot is useful for orientation,
but it is not enough by itself for historical reconciliation.

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
```

Later category commands:

```text
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
bankbuddy account add
bankbuddy bank list
bankbuddy bank rename BANK_ID --name NAME
bankbuddy account list
bankbuddy account update ACCOUNT_ID --display-name NAME
bankbuddy account summary
bankbuddy account show ACCOUNT_ID
bankbuddy account show ACCOUNT_ID --show-full-account-number
bankbuddy account ref add --account-id ACCOUNT_ID --type TYPE --value VALUE
bankbuddy account ref add --account-id ACCOUNT_ID --type TYPE --value VALUE --source-format FORMAT
bankbuddy account ref list
bankbuddy account ref remove REF_ID
bankbuddy export sqlite --output FILE
bankbuddy export sqlite --output FILE --force
```

`account list`, `account summary`, and `account show` use aligned
human-readable output and mask account numbers by default. `account show
--show-full-account-number` is the explicit one-account reveal path for
checking the stored actual account number. `account summary` and `account show`
also expose latest statement-derived balance snapshots, as-of dates, and
source files. `account ref add --help` should include copyable examples for
product identity refs such as Apple Card, last-four suffix refs, and full
account number refs.

`bank rename` changes the configured bank label used in future command output
and account matching by bank name. Historical archived file paths are not
renamed. `account update --display-name` changes only the friendly account
label; stored actual account numbers remain immutable from the CLI.

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

## 13. TaxBuddy Direction

TaxBuddy is the planned tax-document readiness layer inside this repository. It
shares the BankBuddy runtime, environment selection, SQLite database, migration
runner, logging rules, and formatting utilities, but it has its own CLI surface
named `taxbuddy` and its own modules under `src/bankbuddy/tax/`.

TaxBuddy should answer operational questions before tax season:

- Which tax documents have been received for a year?
- Which institutions, employers, properties, or accounts usually produce tax
  forms?
- Which expected forms are still missing, waived, or marked for review?
- Which jurisdiction does each document belong to?

TaxBuddy does not file taxes, prepare returns, transmit data to tax agencies,
or calculate final tax liability. Early summaries are readiness summaries, not
tax advice. Numeric liability estimation requires a separate design for
jurisdiction-specific rules and disclaimers.

### 13.1 Storage Model

TaxBuddy uses the same SQLite database as BankBuddy so account, institution,
and document history can be linked without a second source of truth.
`BANKBUDDY_HOME` continues to select the data home and database. Tax documents
default to a `tax/` subtree under the active data home:

```text
~/BankBuddy/
|-- database/
|   `-- bankbuddy.sqlite3
|-- bank/
|   |-- inbox/
|   |-- processed/
|   |-- duplicates/
|   `-- exports/
|-- tax/
|   |-- inbox/
|   |-- processed/
|   |   `-- us/
|   |       `-- 2025/
|   |           `-- 1099-int/
|   |               `-- ramesh_2025_1099-int_bank-of-america_1234.pdf
|   |-- duplicates/
|   `-- exports/
```

An optional `TAXBUDDY_DOCUMENT_HOME` override may point the tax document root
to an iCloud Drive folder or another synced location for spouse access. That
override must not silently move the SQLite database; if the user wants the
database in a synced location, they must choose that explicitly with
`BANKBUDDY_HOME`. This keeps local-only operation as the default.

Tax imports should use the same file-handling contract as statement imports:
content-based detection rather than source filename inference, SHA-256
idempotency, canonical archive names, dry-run parity, and no destructive moves
until the managed copy is safe. The first TaxBuddy slice skips exact duplicate
documents by hash; preserving duplicate tax files under `tax/duplicates/` can
be added later if the workflow needs that audit trail.

### 13.2 Tax Tables

The first design can use these tables or normalized equivalents:

#### `tax_documents`

| Column | Type | Notes |
|---|---|---|
| `tax_document_id` | INTEGER PK | Surrogate key |
| `file_hash` | TEXT NOT NULL UNIQUE | SHA-256 of document contents |
| `original_file_name` | TEXT NOT NULL | User-supplied filename |
| `canonical_file_name` | TEXT NOT NULL | Parser-derived archive filename |
| `source_path` | TEXT | Explicit import source path when known |
| `processed_path` | TEXT NOT NULL | Path relative to the data home, such as `tax/processed/...` |
| `document_type` | TEXT NOT NULL | Form type such as `1099-INT`, `W-2`, `form_26as`, or `ais` |
| `jurisdiction` | TEXT NOT NULL | ISO-style jurisdiction code such as `US` or `IN` |
| `tax_year` | INTEGER NOT NULL | Tax year represented by the document |
| `source_entity` | TEXT | Issuer such as bank, broker, employer, county, or tax authority |
| `person_label` | TEXT | Optional household/person label used in canonical filenames |
| `account_ref` | TEXT | Masked suffix or parser-visible account reference |
| `imported_at` | DATETIME NOT NULL | |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

Raw extracted text should not be stored durably by default. If searchable
document text becomes useful later, it needs a separate encrypted-storage
design.

#### `tax_sources`

| Column | Type | Notes |
|---|---|---|
| `tax_source_id` | INTEGER PK | Surrogate key |
| `source_name` | TEXT NOT NULL | e.g. `Fidelity`, `Bank of America`, employer name, county name |
| `source_type` | TEXT NOT NULL | `bank`, `brokerage`, `employer`, `property`, `tax_authority`, or `other` |
| `jurisdiction` | TEXT NOT NULL | `US`, `IN`, or another supported jurisdiction |
| `active` | BOOLEAN NOT NULL | False when the relationship is closed |
| `notes` | TEXT | User notes or parser review comments |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

Expected forms and account references may be normalized into child tables rather
than stored as JSON arrays. The important contract is that user overrides are
durable and do not require deleting history.

#### `tax_profile`

| Column | Type | Notes |
|---|---|---|
| `tax_profile_id` | INTEGER PK | Surrogate key |
| `tax_year` | INTEGER NOT NULL | |
| `filing_status` | TEXT | Optional user-maintained value |
| `has_rental_property` | BOOLEAN | Inferred or user-confirmed |
| `has_investments` | BOOLEAN | Inferred or user-confirmed |
| `has_self_employment` | BOOLEAN | Inferred or user-confirmed |
| `has_india_income` | BOOLEAN | Inferred or user-confirmed |
| `notes` | TEXT | Free-form review notes |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

#### `property_assets`

| Column | Type | Notes |
|---|---|---|
| `property_id` | INTEGER PK | Surrogate key |
| `display_name` | TEXT NOT NULL | Human-readable property label |
| `jurisdiction` | TEXT NOT NULL | Country or tax jurisdiction |
| `address` | TEXT | Optional; may be sensitive |
| `purchase_date` | DATE | Optional |
| `property_type` | TEXT | `residential`, `commercial`, `land`, or `other` |
| `active` | BOOLEAN NOT NULL | False when sold or no longer relevant |
| `notes` | TEXT | |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

Cost basis, depreciation, rental-day allocation, and final tax calculations are
out of scope until TaxBuddy has reliable document inventory and gap tracking.

#### `tax_form_gaps`

| Column | Type | Notes |
|---|---|---|
| `tax_form_gap_id` | INTEGER PK | Surrogate key |
| `tax_year` | INTEGER NOT NULL | |
| `tax_source_id` | INTEGER FK | Expected source |
| `expected_document_type` | TEXT NOT NULL | e.g. `1099-INT`, `W-2`, `form_26as` |
| `expected_by_date` | DATE | Typical deadline when known |
| `received_tax_document_id` | INTEGER FK | Null until matched |
| `status` | TEXT NOT NULL | `pending`, `received`, `waived`, or `review` |
| `notes` | TEXT | User or parser review context |
| `created_at` | DATETIME NOT NULL | |
| `updated_at` | DATETIME NOT NULL | |

Gap detection must never fabricate certainty. Ambiguous expectations are review
items until a user confirms or waives them.

### 13.3 TaxBuddy Import Flow

1. Import one explicit file or scan `tax/inbox/`.
2. Compute file hash and skip exact duplicates before parser work.
3. Extract text from text-selectable PDFs or supported fixture text. OCR is
   later work.
4. Detect jurisdiction, document type, tax year, source entity, account
   reference, and optional person label from document content.
5. Fail loudly when required metadata is ambiguous; do not infer from the
   source filename alone.
6. Resolve document source metadata from content. The first implementation
   stores source text as document metadata only; normalized source/profile
   tables come with the gap-detection slice.
7. Copy the document into the canonical `tax/processed/...` hierarchy.
8. Record the `tax_documents` row in one transaction.
9. In dry-run mode, report the same parser, duplicate, canonical path, and
   source-resolution plan without writing rows or copying/removing files.

### 13.4 Planned `taxbuddy` CLI Surface

```text
taxbuddy status
taxbuddy import --file FILE
taxbuddy import --dry-run --file FILE
taxbuddy import inbox
taxbuddy import --dry-run inbox
taxbuddy docs list --year YEAR
taxbuddy docs list --type DOCUMENT_TYPE
taxbuddy docs show TAX_DOCUMENT_ID
```

Later TaxBuddy slices add:

```text
taxbuddy profile show --year YEAR
taxbuddy profile sources
taxbuddy profile gaps --year YEAR
taxbuddy summary --year YEAR
taxbuddy source add
taxbuddy source deactivate SOURCE_ID
taxbuddy gap waive GAP_ID
```

All output follows the same privacy rules as `bankbuddy`: no full account
numbers, SSN-like values, PAN-like values, or raw tax document text in logs or
normal CLI output. The command surface should prefer deterministic, inspectable
tables over hidden inference.

### 13.5 TaxBuddy Implementation Slices

Issue #99 implements the first slice: `taxbuddy` console script, tax document
paths, document metadata indexing, dry-run import, idempotency by file hash,
canonical archival, and `docs list/show`.

Issue #100 should implement the second slice: source/form expectations,
manual overrides, gap generation, waivers, inactive sources, and annual
readiness summaries. Numeric tax-liability estimation remains out of scope.

---

## 14. Phased Roadmap

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
- `tx list` with account, bank, currency, date, debit/credit, sort, view,
  format, category, uncategorized, and summary controls
- `category list` and manual `tx categorize`
- `audit statements` for imported statement coverage sanity checks
- canonical import file names and managed archive copies for explicit imports
- `report spending`
- `export sqlite`
- local tests for parser, normalization, migrations, and CLI smoke paths

### Phase 2 — Broader Import Correctness

- inbox scanning with BOA PDF account auto-routing
- account setup/list commands
- retry failed imports
- ICICI `.xls` statement parser with INR transactions and latest balance snapshot
- HDFC `.xls` statement parser with INR transactions and latest balance snapshot
- HDFC and ICICI PDF parser spikes using real samples
- interactive PDF password prompt
- additional INR import paths through Indian bank parsers
- transfer candidate detection

### Phase 3 — Categorization and Budgets

- category rule management
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

### Phase 5 — TaxBuddy Document Readiness

- `taxbuddy` console script using shared runtime and database conventions
- tax document inbox, processed archive, duplicates, and exports under the
  active data home
- optional configured tax document root for iCloud or other synced storage
- text-selectable PDF metadata extraction for initial tax document types
- `tax_documents` index and source/profile storage
- tax document dry-run import with canonical archive planning
- expected-form gap detection and annual readiness summary
- explicit non-goal: tax filing or numeric tax liability estimation

### Phase 6 — Interfaces

- read-only web dashboard
- charts for spending, income, budgets, and tax readiness
- later web recategorization/budget management
- local iOS viewer via Xcode-installed app

---

## 15. Design Principles

- **Correctness before breadth.** One reliable parser is better than three
  fragile ones.
- **Fail loudly, not silently.** Ambiguous bank, account, amount, or date data
  should stop the import or become an explicit review item.
- **Never pollute the transaction table.** Parse and validate before commit.
- **Money is integer data.** Store minor units, never floats.
- **Retries are normal.** Failed imports should be visible and retryable.
- **Local first.** Cloud, LLM, and sync features are opt-in later layers.
- **Readiness, not advice.** TaxBuddy organizes documents and gaps; tax filing
  and liability calculation require separate designs.
- **Extensible without ceremony.** Parser modules should be easy to add, but the
  first implementation should stay small.

---

## 16. Out of Scope for Phase 1

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
- Tax document import, tax filing, or tax liability estimation

---

*Document generated from design discussion and review. Ready for Phase 0
implementation planning.*
