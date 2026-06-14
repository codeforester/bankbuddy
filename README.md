# bankbuddy

Local-first personal finance tracking.

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
bankbuddy account list
bankbuddy import --dry-run --file path/to/boa.pdf --account-id 1
bankbuddy import --file path/to/boa.pdf --account-id 1
bankbuddy import --dry-run inbox
bankbuddy import inbox
bankbuddy import inbox --account-id 1
bankbuddy import history
bankbuddy import history --status duplicate
bankbuddy import history --status failed
bankbuddy import history --status success --limit 10
bankbuddy import retry 1
bankbuddy import retry 1 --account-id 1
bankbuddy tx list
bankbuddy tx list --direction debit
bankbuddy tx list --direction credit
bankbuddy tx list --sort date:desc,amount
bankbuddy tx list --sort amount --order desc
bankbuddy tx list --view compact
bankbuddy tx list --view ledger
bankbuddy tx list --format csv
bankbuddy tx list --format tsv
bankbuddy tx list --summary
bankbuddy tx list --account-id 1 --from 2026-04-01 --to 2026-05-31
bankbuddy report spending --year 2026
bankbuddy report spending --year 2026 --month 5
bankbuddy export sqlite --output ~/Desktop/bankbuddy-backup.sqlite3
bankbuddy export sqlite --output ~/Desktop/bankbuddy-backup.sqlite3 --force
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

`BANKBUDDY_HOME` is a data-home override for the database and managed folders
such as `inbox`, `processed`, `duplicates`, and `exports`. It does not point to
the source checkout. When set, it wins over the environment-to-home mapping
while `BANKBUDDY_ENV` still names the active environment.

Use Base-style runtime options before the subcommand when troubleshooting:

```bash
bankbuddy --debug status
bankbuddy -v --log-file /tmp/bankbuddy.log import \
  --file path/to/boa.pdf \
  --account-id 1
```

Primary command output goes to stdout. Runtime diagnostics go to stderr, and
debug logs avoid full account numbers and raw statement contents.

Bank of America imports support text-selectable PDF statements first, plus CSV
files when available. BOA PDF period extraction supports the statement-period
header and the account header found in eStatement text. BOA PDF files in
`~/BankBuddy/inbox/` can be routed to a configured account by statement account
number; CSV inbox imports still require `--account-id` unless the file is an
exact duplicate of a prior successful import. Successful imports are copied into
`~/BankBuddy/processed/<bank>/<year>/<month>/` with canonical filenames while
the original source files are left untouched. Exact duplicate inbox files are
identified by SHA-256 file hash before parser work, recorded as `duplicate`
attempts, and moved to `~/BankBuddy/duplicates/<bank>/<year>/<month>/` for now.
Use `bankbuddy import --dry-run ...` to preview parser, duplicate, and archive
actions without writing transactions, import history, processed files, duplicate
files, or removing inbox files.
Keep real statements outside the repo; Bank Buddy stores data in your local
SQLite database.

Supported import failures are recorded in `import history`. Retrying a failed
attempt creates a new attempt and leaves the original failed attempt intact.

SQLite exports contain sensitive financial data and actual account numbers.
Store them in a private location.

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
