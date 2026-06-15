# BankBuddy Project Context

BankBuddy is a local-first personal finance tracking project. It helps a
technically comfortable user import bank statements, inspect transactions,
track categories and spending, audit statement coverage, and keep sensitive
financial data under local control.

TaxBuddy is the tax document readiness layer in the same repository. It shares
the Python package and SQLite database, but exposes a separate `taxbuddy` CLI.
Its current scope is document indexing and readiness, not tax filing, return
preparation, or final tax liability calculation.

## Product Shape

- Core language: Python 3.12+.
- Project tooling: `uv`, `pyproject.toml`, and a Base manifest.
- CLI framework: Click with Base-style runtime conventions.
- Database: local SQLite with packaged migrations.
- Data model: banks, accounts, categories, transactions, import files, import
  attempts, account statement refs, account balance snapshots, and tax
  documents.
- Storage: local data homes with `database/`, `bank/`, and `tax/` directories.
- Distribution status: version `0.1.0`, still pre-1.0 and evolving quickly.

## Current Users

The target user is digitally savvy: comfortable downloading statements from
banks, running CLI commands, and reviewing local files. The project is built
for personal use first, then friends, then possibly broader distribution.

## Privacy Posture

BankBuddy does not store bank credentials and does not require cloud sync.
Statement files, SQLite data, exports, and tax documents stay local by default.
CLI output and logs should mask full account numbers unless the user explicitly
requests one-account inspection.

## Base Relationship

This is a Base-managed project named `bankbuddy`. `base_manifest.yaml` declares:

- `Brewfile` setup.
- `.base/activate.sh` as the activation hook.
- `./tests/validate.sh` as the Base test command.

Base activation defaults development shells to `BANKBUDDY_ENV=dev` when the
user has not already chosen an environment.
