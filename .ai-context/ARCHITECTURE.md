# BankBuddy Architecture Context

## Repository Layout

- `src/bankbuddy/` contains banking domain code, the `bankbuddy` CLI, shared
  runtime helpers, SQLite access, migrations, importers, reports, and storage
  layout code.
- `src/bankbuddy/tax/` contains the TaxBuddy document-readiness slice.
- `src/bankbuddy/migrations/` contains ordered SQL migrations.
- `tests/` contains pytest coverage and `tests/validate.sh`.
- `base_manifest.yaml` is the Base project contract. It declares BankBuddy as
  a uv-managed Python project and routes selected project commands through
  Base's `runner: uv` support.
- `bank_buddy_spec.md` is the broader design and architecture specification.
- `docs/financial_intelligence_architecture_review.md` is the current v2
  architecture direction for evolving BankBuddy into a local-first personal
  financial intelligence platform.

## Runtime Model

The CLIs use Click but follow Base-style runtime behavior:

- Root options such as `--debug`, `--log-file`, `--keep-temp`,
  `--environment`, and `--config` are handled before subcommands.
- Primary command output goes to stdout.
- Diagnostics and debug logs go to stderr or the selected log file.
- Diagnostics should avoid full account numbers and raw statement contents.

## Data Homes

BankBuddy environments are local data homes, not source checkouts.

- `prod` maps to `~/BankBuddy`.
- `dev` maps to `~/BankBuddy-dev`.
- Other environment names map to `~/BankBuddy-<name>`.
- `BANKBUDDY_HOME` overrides the data-home path.
- `--environment` overrides the environment for one command.
- `BANKBUDDY_ENV` selects the environment for a shell session.

New data homes use:

- `database/bankbuddy.sqlite3` for SQLite.
- `bank/inbox`, `bank/processed`, `bank/duplicates`, and `bank/exports` for
  banking statements and exports.
- Matching `tax/` folders for tax document workflows.

## Banking Import Model

Imports are content-driven. BankBuddy uses parser-detected bank, currency,
account numbers, and configured account statement refs to resolve a statement
to exactly one configured account. Source filenames are not trusted for account
identity.

Supported current statement inputs include:

- Bank of America text-selectable PDF statements.
- Bank of America CSV exports when available.
- Apple Card text-selectable PDF statements using configured product refs.
- ICICI Bank old Excel `.xls` exports.
- HDFC Bank old Excel `.xls` exports.

Dry-run imports parse and plan without writing database rows or moving files.
Real imports record import attempts, persist parsed rows, archive successful
files under canonical managed paths, and identify exact duplicate inbox files
by SHA-256 hash.

## TaxBuddy Model

TaxBuddy shares BankBuddy paths, runtime, SQLite migrations, and table rendering
style. The first slice indexes tax documents from explicit files or the tax
inbox, extracts conservative metadata, archives documents under
`tax/processed/<jurisdiction>/<year>/<type>/`, and lists or shows indexed
metadata.

Raw extracted tax document text is not stored durably. Gap detection, expected
forms, OCR, synced document roots, tax calculations, and filing support are
future work unless a focused issue says otherwise.

## Financial Intelligence V2 Direction

The accepted v2 direction keeps the product and CLI name as `bankbuddy` while
moving the long-term architecture toward `Document`, `Entity`, `Observation`,
and `Relationship` foundations. New schema proposals use `BB_`-prefixed
singular table names and prefer normalized relational tables over JSON blobs.

TaxBuddy issue #100 is paused until the v2 document/entity/observation model
exists. Early v2 work should focus on a schema reset path, generic document
storage/import, provenance, and inspect/report foundations before adding a
user-facing infer workflow.
