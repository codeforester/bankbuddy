# bankbuddy

Local-first personal finance tracking.

## License

Copyright (C) 2026 Ramesh Padmanabhaiah

bankbuddy is free software: you can redistribute it and/or modify it under the
terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

bankbuddy is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU Affero General Public License for more
details.

You should have received a copy of the GNU Affero General Public License along
with bankbuddy. If not, see <https://www.gnu.org/licenses/>.

Versions before this relicensing change remain available under the MIT License
as originally published. New versions are licensed under AGPL-3.0-or-later.

## Development

Install project tools through Base:

```bash
basectl setup bankbuddy
```

Set up the Python environment with `uv`:

```bash
uv sync
```

Activate the project shell once, then run the CLI directly:

```bash
basectl activate bankbuddy
bankbuddy --help
bankbuddy status
bankbuddy init
bankbuddy account add \
  --bank "Bank of America" \
  --country US \
  --account-number "<actual-number>" \
  --type checking \
  --currency USD
bankbuddy account add \
  --bank "ICICI Bank" \
  --country IN \
  --account-number "<actual-number>" \
  --type savings \
  --currency INR
bankbuddy account add \
  --bank "HDFC Bank" \
  --country IN \
  --account-number "<actual-number>" \
  --type savings \
  --currency INR
bankbuddy bank list
bankbuddy bank rename BANK_ID --name "Apple Card"
bankbuddy account list
bankbuddy account update ACCOUNT_ID --display-name "Apple Card"
bankbuddy account summary
bankbuddy account show 1
bankbuddy account show 1 --show-full-account-number
bankbuddy account ref add --account-id 1 --type last4 --value 1145
bankbuddy account ref add \
  --account-id 1 \
  --type product \
  --value "Apple Card" \
  --source-format apple_card_pdf
bankbuddy account ref list
bankbuddy import --dry-run --file path/to/boa.pdf --account-id 1
bankbuddy import --file path/to/boa.pdf --account-id 1
bankbuddy import --dry-run --file path/to/icici.xls --account-id 2
bankbuddy import --file path/to/icici.xls --account-id 2
bankbuddy import --dry-run --file path/to/hdfc.xls --account-id 3
bankbuddy import --file path/to/hdfc.xls --account-id 3
bankbuddy import --dry-run inbox
bankbuddy import inbox
bankbuddy import inbox --account-id 1
bankbuddy import history
bankbuddy import history --status duplicate
bankbuddy import history --status failed
bankbuddy import history --status success --limit 10
bankbuddy import retry 1
bankbuddy import retry 1 --account-id 1
bankbuddy statements summary
bankbuddy statements summary --by month --years 2024,2025
bankbuddy statements summary --bank "Bank of America" --account-last4 1145
bankbuddy statements list
bankbuddy statements list --year 2025 --account-last4 1145
bankbuddy tx list
bankbuddy tx list --bank "Bank of America"
bankbuddy tx list --currency USD
bankbuddy tx list --account-number "<actual-number>"
bankbuddy tx list --account-last4 1145
bankbuddy tx list --direction debit
bankbuddy tx list --direction credit
bankbuddy tx list --sort date:desc,amount
bankbuddy tx list --sort amount --order desc
bankbuddy tx list --view compact
bankbuddy tx list --view ledger
bankbuddy tx list --format csv
bankbuddy tx list --format tsv
bankbuddy tx list --summary
bankbuddy category list
bankbuddy tx categorize 1 Groceries
bankbuddy tx list --category Groceries
bankbuddy tx list --uncategorized
bankbuddy tx list --account-id 1 --from 2026-04-01 --to 2026-05-31
bankbuddy audit statements --years 2025
bankbuddy audit statements --bank "HDFC Bank" --years 2025
bankbuddy audit statements --years 2024,2025 --account-last4 1145
bankbuddy audit statements --from 2025-01-01 --to 2025-12-31
bankbuddy report spending --year 2026
bankbuddy report spending --year 2026 --month 5
bankbuddy export sqlite --output ~/Desktop/bankbuddy-backup.sqlite3
bankbuddy export sqlite --output ~/Desktop/bankbuddy-backup.sqlite3 --force
bankbuddy storage migrate-layout --dry-run
bankbuddy storage migrate-layout --apply
taxbuddy status
taxbuddy import --dry-run --file path/to/1099-int.pdf
taxbuddy import --file path/to/1099-int.pdf
taxbuddy import --dry-run inbox
taxbuddy import inbox
taxbuddy docs list
taxbuddy docs list --year 2025
taxbuddy docs list --type 1099-INT
taxbuddy docs show 1
```

## Environments

BankBuddy keeps separate local data homes for named environments. Outside an
activated project shell, the CLI defaults to `prod` at `~/BankBuddy`. A Base
activated BankBuddy shell defaults to `dev` by exporting `BANKBUDDY_ENV=dev`,
which maps to `~/BankBuddy-dev`.

Use `status` to confirm the active environment and database:

```bash
bankbuddy status
```

Switch the current shell by exporting `BANKBUDDY_ENV`:

```bash
export BANKBUDDY_ENV=prod
bankbuddy status

export BANKBUDDY_ENV=dev
bankbuddy status
```

For a one-command override, use `--environment` before the subcommand:

```bash
bankbuddy --environment prod status
bankbuddy --environment dev import inbox
```

`BANKBUDDY_HOME` is a data-home override for the database and managed folders.
It does not point to the source checkout. New homes use
`database/bankbuddy.sqlite3` for SQLite and `bank/inbox`, `bank/processed`,
`bank/duplicates`, and `bank/exports` for statement files, plus matching
`tax/` folders for the planned tax document workflow. When set,
`BANKBUDDY_HOME` wins over the environment-to-home mapping while
`BANKBUDDY_ENV` still names the active environment.

Use Base-style runtime options before the subcommand when troubleshooting:

```bash
bankbuddy --debug status
bankbuddy -v --log-file /tmp/bankbuddy.log import \
  --file path/to/boa.pdf \
  --account-id 1
```

Primary command output goes to stdout. Runtime diagnostics go to stderr, and
debug logs avoid full account numbers and raw statement contents.

`bankbuddy tx list` can filter by `--account-id`, `--bank`, `--currency`,
`--account-number`, `--account-last4`, date range, debit/credit direction,
`--category`, and `--uncategorized`. Full account numbers are accepted for
filtering, but transaction output keeps using display names or masked account
suffixes.

`bankbuddy account list`, `account summary`, and `account show` mask account
numbers by default. Use `bankbuddy account show ACCOUNT_ID
--show-full-account-number` only when you need to inspect the stored actual
account number for one account.

Use `bankbuddy bank list` and `bankbuddy bank rename BANK_ID --name NAME` to
fix bank labels such as `Apple GS` versus `Apple Card`. Use `bankbuddy account
update ACCOUNT_ID --display-name NAME` to adjust a friendly account label
without changing the stored actual account number.

`bankbuddy category list` shows the built-in categories. Use
`bankbuddy tx categorize TRANSACTION_ID CATEGORY` to manually assign one
transaction to an existing category, then review with `tx list --category ...`
or `tx list --uncategorized`.

`bankbuddy statements summary` and `bankbuddy statements list` inspect imported
statement-file inventory. `summary` groups successful statement files by
statement end year by default, or by statement end month with `--by month`.
Both commands are read-only, use successful imports with configured accounts
and statement start/end dates, and can be filtered with `--bank`,
`--account-id`, and `--account-last4`.

`bankbuddy audit statements` checks imported statement-period metadata for
missing gaps, overlapping periods, duplicate periods, and covered periods.
Use `--years YYYY[,YYYY...]` for independent calendar-year windows or
`--from YYYY-MM-DD --to YYYY-MM-DD` for one explicit range. The audit is
read-only and can be narrowed with `--bank`, `--account-id`, or
`--account-last4`.

Statement import routing is based on content extracted from the file, not the
source filename. BankBuddy uses parser-detected bank, currency, account number,
and configured `account ref` values to map a statement to one account. If an
explicit `--account-id` is supplied and a document identity maps to a different
configured account, the import fails instead of trusting the flag.

Bank of America imports support text-selectable PDF statements first, plus CSV
files when available. BOA PDF period extraction supports the statement-period
header and the account header found in eStatement text. BOA PDF files in
`~/BankBuddy/bank/inbox/` can be routed to a configured account by statement
account number; CSV inbox imports still require `--account-id` unless the file
is an exact duplicate of a prior successful import.

Apple Card imports support text-selectable PDF statements. BankBuddy detects
Apple Card PDFs from document content, routes them with configured product refs
such as `Apple Card`, imports purchases as debits and payments/credits as
credits, and keeps zero-activity statements in the processed archive.

ICICI Bank and HDFC Bank imports support old Excel `.xls` statement exports.
These `.xls` files can be routed from `bank/inbox/` by the full account number
in the spreadsheet when exactly one configured INR account for that bank
matches.
Successful spreadsheet imports store transaction value dates and update the
account latest balance snapshot from the statement balance.

Successful imports are copied into
`~/BankBuddy/bank/processed/<bank>/<year>/<month>/` with canonical filenames
while the original explicit source files are left untouched. Exact duplicate
inbox files are identified by SHA-256 file hash before parser work, recorded
as `duplicate` attempts, and moved to
`~/BankBuddy/bank/duplicates/<bank>/<year>/<month>/` for now.
Use `bankbuddy import --dry-run ...` to preview parser, duplicate, and archive
actions without writing transactions, import history, processed files, duplicate
files, or removing inbox files.
Keep real statements outside the repo; Bank Buddy stores data in your local
SQLite database.

Existing homes created before the canonical `database/` and `bank/` layout can
be migrated with `bankbuddy storage migrate-layout --dry-run`, then
`bankbuddy storage migrate-layout --apply` after reviewing the plan.

Supported import failures are recorded in `import history`. Retrying a failed
attempt creates a new attempt and leaves the original failed attempt intact.

SQLite exports contain sensitive financial data and actual account numbers.
Store them in a private location.

## TaxBuddy Roadmap

BankBuddy is the banking CLI. TaxBuddy is the tax document readiness CLI in the
same repo and SQLite database. The first `taxbuddy` slice indexes received tax
documents under the active `BANKBUDDY_HOME`, archives them under
`tax/processed/<jurisdiction>/<year>/<type>/`, and lets you inspect the index
without opening SQLite.

Supported MVP imports use content extracted from text-selectable PDFs or `.txt`
fixtures. TaxBuddy currently detects conservative metadata for forms such as
`1099-INT`, `1099-DIV`, `1099-B`, `W-2`, `FORM_26AS`, and `AIS`: jurisdiction,
tax year, source entity, and an optional account suffix. Ambiguous document
type, year, jurisdiction, or source fails clearly instead of guessing from the
source filename.

Use `taxbuddy import --dry-run --file FILE` or `taxbuddy import --dry-run inbox`
to preview metadata, duplicate-by-hash decisions, and canonical archive paths
without writing the database or copying/removing files. Real imports are
idempotent by SHA-256 file hash. Raw extracted tax document text is not stored
durably.

TaxBuddy will not file taxes, prepare returns, or calculate final tax
liability. Local storage remains the default. An iCloud or other synced tax
document folder may be configured later for spouse access, but sync is opt-in
and does not silently move the SQLite database.

The remaining planned work is tracked in GitHub issue #100 for expected-form
gap detection and annual readiness summaries.

Run tests:

```bash
uv run pytest
./tests/validate.sh
```

## Base

This repository is managed by [Base](https://github.com/codeforester/base).

Common commands:

```bash
basectl setup bankbuddy
basectl check bankbuddy
basectl doctor bankbuddy
basectl test bankbuddy
```
