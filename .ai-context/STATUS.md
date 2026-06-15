# BankBuddy Status Context

## Current Version

BankBuddy is at version `0.1.0` and remains pre-1.0. The active changelog
section is `Unreleased`.

## Current Product Capabilities

- Base-managed setup, activation, and validation.
- Local SQLite initialization and ordered migrations.
- Local data homes for `prod`, `dev`, and named environments.
- Banking CLI commands for banks, accounts, statement refs, imports,
  transactions, categories, reports, exports, storage migration, and status.
- Supported banking imports for Bank of America PDF/CSV, Apple Card PDF, ICICI
  `.xls`, and HDFC `.xls`.
- Statement inventory and statement coverage auditing.
- TaxBuddy document indexing with dry-run planning, SHA-256 idempotency,
  canonical tax archive paths, and `docs list/show`.

## Recent Major Changes

- Prospective relicensing from MIT to AGPL-3.0-or-later.
- Canonical data-home layout with `database/`, `bank/`, and `tax/` directories.
- First TaxBuddy CLI slice and `tax_documents` metadata index.
- Storage layout migration command for legacy homes.
- Apple Card PDF import support and product-ref routing.
- Content-based statement routing through configured account refs.
- ICICI and HDFC `.xls` import support with INR transactions and value dates.
- Statement coverage audits and statement inventory views.
- Dry-run import planning and duplicate inbox handling.

## Active Roadmap

The next TaxBuddy area is expected-form gap detection and annual readiness
summaries. That work introduces persisted inference state and should have a
small issue-backed design/spec pass before implementation.

## Validation Snapshot

Use these commands before publishing meaningful changes:

```bash
./tests/validate.sh
git diff --check
```

Run narrower pytest targets first for focused parser, CLI, migration, runtime,
or storage changes.
