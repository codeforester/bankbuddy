# Changelog

All notable changes to bankbuddy will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions are tracked in the repo-root `VERSION` file.

## [Unreleased]

### Added

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

- Renamed the installed CLI command from `bank-buddy` to `bankbuddy` and removed
  the dashed command name.
