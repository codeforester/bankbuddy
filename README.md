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

Run the CLI:

```bash
uv run bank-buddy --help
uv run bank-buddy status
uv run bank-buddy init
uv run bank-buddy account add \
  --bank "Bank of America" \
  --country US \
  --account-number "<actual-number>" \
  --type checking \
  --currency USD
uv run bank-buddy account list
uv run bank-buddy import --file path/to/boa.pdf --account-id 1
uv run bank-buddy import inbox --account-id 1
uv run bank-buddy import history
uv run bank-buddy import history --status success --limit 10
uv run bank-buddy tx list
uv run bank-buddy tx list --account-id 1 --from 2026-04-01 --to 2026-05-31
uv run bank-buddy report spending --year 2026
uv run bank-buddy report spending --year 2026 --month 5
uv run bank-buddy export sqlite --output ~/Desktop/bankbuddy-backup.sqlite3
uv run bank-buddy export sqlite --output ~/Desktop/bankbuddy-backup.sqlite3 --force
```

Use Base-style runtime options before the subcommand when troubleshooting:

```bash
uv run bank-buddy --debug status
uv run bank-buddy -v --log-file /tmp/bank-buddy.log import \
  --file path/to/boa.pdf \
  --account-id 1
```

Primary command output goes to stdout. Runtime diagnostics go to stderr, and
debug logs avoid full account numbers and raw statement contents.

Bank of America imports support text-selectable PDF statements first, plus CSV
files when available. Successful imports are copied into
`~/BankBuddy/processed/<bank>/<year>/<month>/` with canonical filenames while
the original source files are left untouched. Keep real statements outside the
repo; Bank Buddy stores data in your local SQLite database.

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
