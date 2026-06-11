# Changelog

All notable changes to bankbuddy will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions are tracked in the repo-root `VERSION` file.

## [Unreleased]

### Added

- Added a project `Brewfile` and Base manifest delegation so
  `basectl setup bankbuddy` can install `uv`.
- Added packaged SQLite migrations for the core schema, including banks,
  accounts, categories, transactions, import files, import attempts,
  category rules, budgets, and built-in seed categories.
- Added the Phase 0 Python project skeleton with `uv`, `pyproject.toml`, a
  Click-based `bank-buddy` CLI, app directory discovery, SQLite migration
  bootstrap, USD/INR currency helpers, pytest coverage, and CI validation.
- Initialized the repository with the Base-managed repo baseline.
