# BankBuddy Durable Decisions

## Local-First Privacy

BankBuddy stores data locally by default. It does not store bank credentials or
require cloud sync. SQLite exports and archived statement files are sensitive
and should remain in private user-controlled locations.

## Python, Click, SQLite, And uv

Python 3.12+, Click, SQLite, and `uv` are the core project contract. The repo
uses a `src/` layout, packaged migrations, and pytest coverage. Base owns
workspace orchestration for this uv-managed project through the
`python.manager: uv` manifest setting and command-level `runner: uv`; uv still
owns dependency resolution and the project-local `.venv`.

## Base-Style Runtime

The CLIs keep Click as the parser while following Base-style runtime behavior:
root runtime options, stdout for primary output, stderr/log files for
diagnostics, and safe debug output.

## Environment Names Are Data Homes

`BANKBUDDY_ENV` names a local data environment; it is not the source checkout.
Base activation defaults development shells to `dev` only when the user has not
already chosen an environment. `BANKBUDDY_HOME` remains an explicit data-home
path override.

## BankBuddy And TaxBuddy Share Infrastructure

TaxBuddy is a second CLI in the same repo and Python package. It shares paths,
runtime helpers, SQLite migrations, and table rendering, but keeps tax document
domain code under `src/bankbuddy/tax/`.

## Content Beats Filename

Statement imports route accounts from parser-detected content and configured
account refs. A filename can help humans organize files, but it is not trusted
as account identity.

## Dry-Run First For Risky Operations

Imports, repairs, and storage-layout migration expose dry-run paths so parser,
duplicate, archive, and migration decisions can be reviewed before writes.

## V2 Canonical Storage And Human Views

The financial-intelligence v2 model stores authoritative document objects under
`financial/canonical` and exposes user-friendly generated copies under
`financial/views`. The database centralizes path metadata in storage roots,
document objects, and document views; domain facts reference document/object
rows instead of embedding filesystem paths. Human views are copies by default,
not symlinks or hardlinks, so they can be rebuilt, reconciled, and repaired
without making user-browsable folders the heart of the system.

## Mask Sensitive Account Details

Full account numbers can be stored for validation and exact matching, but
normal command output should use display names or masked suffixes. Explicit
one-account inspection is allowed when the command makes the reveal obvious.

## TaxBuddy Is Readiness, Not Filing

TaxBuddy organizes tax documents and will surface expected-form gaps and annual
readiness summaries. It does not prepare returns, file taxes, or calculate
final tax liability.

## AI Context Is Curated

`.ai-context/` is a manually curated orientation layer for AI tools. Canonical
docs and code remain the source of truth.
