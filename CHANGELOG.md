# Changelog

All notable changes to bankbuddy will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions are tracked in the repo-root `VERSION` file.

## [Unreleased]

### Changed

- Moved the README license notice out of the opening project summary.
- Relicensed bankbuddy prospectively from MIT to AGPL-3.0-or-later.

### Fixed

- Added a dry-run-first repair command for historical Bank of America PDF
  imports affected by the PDF transaction identity change, including safe hash
  backfill and insertion of previously skipped legitimate rows.
- Fixed Bank of America PDF parsing so continuation lines such as `ID:...`
  are included in transaction identity instead of collapsing distinct same-day
  same-amount rows into skipped duplicates.
- Fixed older Bank of America PDF statement-period extraction for combined
  statement headers and legacy page headers, and made unsupported period
  layouts report the expected header shapes.
- Fixed Bank of America PDF statement-period extraction for eStatement account
  headers that use `for <date> to <date> Account number`.

### Added

- Added the first `taxbuddy` CLI slice with tax document import, dry-run
  planning, SHA-256 idempotency, canonical `tax/processed/...` archival,
  `tax_documents` metadata indexing, and `taxbuddy docs list/show`.
- Added `bankbuddy storage migrate-layout --dry-run|--apply` for moving legacy
  app homes into the canonical `database/` and `bank/` storage layout while
  updating stored archive paths.
- Documented the planned TaxBuddy layer, including the second `taxbuddy` CLI,
  shared SQLite/database boundary, local-first tax document storage, readiness
  scope, and follow-on implementation issues.
- Added `bankbuddy bank list`, `bankbuddy bank rename`, and
  `bankbuddy account update --display-name` for correcting configured bank and
  account display labels without changing stored account numbers.
- Added Apple Card PDF imports with content-based PDF routing, product-ref
  account matching, credit-card sign normalization, zero-activity statement
  support, and latest statement balance snapshots.
- Added concrete examples to `bankbuddy account ref add --help` for Apple Card
  product refs, last-four statement suffix refs, and full account number refs.
- Added `bankbuddy account show --show-full-account-number` for explicit
  one-account inspection of the stored actual account number.
- Added `account_statement_refs` and `bankbuddy account ref` commands for
  content-based statement account routing, including explicit-account mismatch
  protection when a document identity maps to another configured account.
- Added `Rental Income` as a built-in system income category for new and
  existing databases.
- Added HDFC Bank `.xls` statement imports with INR transactions, value-date
  storage, row-balance sanity checks, inbox account auto-routing, account-level
  latest balance snapshots, and boundary-row deduplication.
- Added `bankbuddy audit statements --bank` for narrowing statement coverage
  audits by bank name.
- Added manual transaction categorization with `bankbuddy category list`,
  `bankbuddy tx categorize`, `bankbuddy tx list --category`, and
  `bankbuddy tx list --uncategorized`.
- Added `bankbuddy account summary` and `bankbuddy account show` for reviewing
  configured accounts, masked account numbers, and latest statement-derived
  balance snapshots with source file metadata.
- Added ICICI Bank `.xls` statement imports with INR transactions, value-date
  storage, row-balance sanity checks, inbox account auto-routing, and
  account-level latest balance snapshots with source file provenance.
- Added `bankbuddy tx duplicates` to reconstruct rows skipped as duplicate
  transactions and show each parsed candidate next to the stored transaction
  that matched it.
- Added `bankbuddy repair statement-imports --source-format ...` as a generic
  dry-run-first statement repair entrypoint, with Bank of America PDF repairs
  routed through a source-format adapter.
- Added `bankbuddy statements summary` and `bankbuddy statements list` for
  read-only inventory views of imported statement files by bank, account, year,
  and month.
- Added `bankbuddy audit statements` for read-only statement coverage checks
  that report missing gaps, overlaps, duplicate periods, and covered periods
  across imported statement metadata.
- Added `bankbuddy tx list --bank`, `--currency`, `--account-number`, and
  `--account-last4` filters for narrowing transaction review by bank, currency,
  exact account number, or unambiguous account suffix.
- Added `bankbuddy tx list --format pretty|csv|tsv`, with `pretty` as the
  aligned default table output and CSV/TSV for clean machine-readable rows.
- Added `bankbuddy tx list --sort`, `--order`, `--view`, and `--summary`
  options for ordering transactions, switching human-readable list views, and
  printing per-currency totals for the filtered result set.
- Added `bankbuddy tx list --direction debit|credit` for filtering outgoing
  negative-amount transactions or incoming positive-amount transactions.
- Added `bankbuddy import --dry-run` for explicit file and inbox imports,
  previewing parser results, duplicate decisions, and canonical archive paths
  without writing database rows or moving statement files.
- Added exact duplicate inbox import detection using SHA-256 file hashes, with
  duplicate attempts recorded in history and duplicate source files preserved
  under the managed `bank/duplicates/` directory.
- Added first-class BankBuddy environments selected by `BANKBUDDY_ENV`, visible
  in `status`, and defaulted to `dev` during Base activation.
- Added durable failed import attempts and an `import retry` command for
  retrying failed imports from recorded source metadata.
- Added account auto-routing for Bank of America PDF files processed by
  `import inbox`, while keeping CSV inbox imports explicit with `--account-id`.
- Added an `import inbox` command for processing supported statement files from
  the managed inbox for an explicit account.
- Added an `export sqlite` command for writing sensitive local SQLite
  backups with overwrite protection.
- Added a `report spending` command for summarizing outgoing transactions by
  category and currency for a year or month.
- Added canonical imported-statement filenames and managed processed-file
  archive copies for successful explicit imports, with original source files
  left untouched.
- Added an `import history` command for inspecting prior import attempts with
  status and limit filters.
- Added a `tx list` command for inspecting imported transactions with account
  and date filters.
- Added Base-style CLI runtime options for debug logging, config loading,
  environment selection, temp preservation, and log-file overrides.
- Added Bank of America text-PDF imports with full-account-number validation
  before transaction writes.
- Added explicit Bank of America CSV imports with transaction hashing,
  duplicate skipping, import attempt records, and CLI summaries.
- Added minimal account setup commands for creating and listing configured bank
  accounts before imports.
- Added a project `Brewfile` and Base manifest delegation so
  `basectl setup bankbuddy` can install `uv`.
- Added packaged SQLite migrations for the core schema, including banks,
  accounts, categories, transactions, import files, import attempts,
  category rules, budgets, and built-in seed categories.
- Added the Phase 0 Python project skeleton with `uv`, `pyproject.toml`, a
  Click-based `bankbuddy` CLI, app directory discovery, SQLite migration
  bootstrap, USD/INR currency helpers, pytest coverage, and CI validation.
- Initialized the repository with the Base-managed repo baseline.

### Changed

- New BankBuddy homes store SQLite at `database/bankbuddy.sqlite3` and banking
  statement files under `bank/inbox`, `bank/processed`, `bank/duplicates`, and
  `bank/exports`, with matching `tax/` folders created for the planned tax
  document workflow.
- Rendered `bankbuddy account list` as the standard aligned pretty table while
  continuing to mask account numbers by default.
- Normalized account bank country values to ISO 3166-1 alpha-2 codes such as
  `US` and `IN`, while accepting common friendly aliases during account setup.
- Hid the advanced `account add --statement-ref` option from normal help so
  full-account-number setup stays clear for supported statement imports.
- Renamed the installed CLI command from `bank-buddy` to `bankbuddy` and removed
  the dashed command name.
