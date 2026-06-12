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
bankbuddy import --file path/to/boa.pdf --account-id 1
bankbuddy import inbox
bankbuddy import inbox --account-id 1
bankbuddy import history
bankbuddy import history --status failed
bankbuddy import history --status success --limit 10
bankbuddy import retry 1
bankbuddy import retry 1 --account-id 1
bankbuddy tx list
bankbuddy tx list --account-id 1 --from 2026-04-01 --to 2026-05-31
bankbuddy report spending --year 2026
bankbuddy report spending --year 2026 --month 5
bankbuddy export sqlite --output ~/Desktop/bankbuddy-backup.sqlite3
bankbuddy export sqlite --output ~/Desktop/bankbuddy-backup.sqlite3 --force
```

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
files when available. BOA PDF files in `~/BankBuddy/inbox/` can be routed to a
configured account by statement account number; CSV inbox imports still require
`--account-id`. Successful imports are copied into
`~/BankBuddy/processed/<bank>/<year>/<month>/` with canonical filenames while
the original source files are left untouched. Keep real statements outside the
repo; Bank Buddy stores data in your local SQLite database.

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
