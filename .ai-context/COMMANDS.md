# BankBuddy Command Context

## Development And Base

Common project setup and validation commands:

```bash
basectl setup bankbuddy
basectl check bankbuddy
basectl doctor bankbuddy
basectl test bankbuddy
basectl run bankbuddy bb -- status
basectl run bankbuddy bankbuddy -- status
basectl run bankbuddy taxbuddy -- status
basectl activate bankbuddy
basectl gh issue create --category enhancement --title "..."
uv sync
uv run pytest
./tests/validate.sh
```

`base_manifest.yaml` declares `python.manager: uv`, so `basectl setup
bankbuddy` delegates to `uv sync`, `basectl activate bankbuddy` uses the
project-local `.venv`, and manifest-declared `test` / `run` commands can opt
into `uv run` through `runner: uv`.

`basectl activate bankbuddy` enters a project shell and sources
`.base/activate.sh`, which defaults `BANKBUDDY_ENV=dev` when unset.

## bb CLI

Run the v2 financial intelligence CLI with:

```bash
bb --help
bb init
bb status
bb documents import --dry-run --file path/to/document.pdf
bb documents import --file path/to/document.pdf
```

`bb` is the side-by-side command surface for new `BB_` schema work. It should
grow new document/entity/observation workflows while the legacy command
surfaces remain available. Use `bb init` to apply current migrations and
prepare v2 `financial/` storage roots for the active data home.
`bb documents import` is parser-free: it hashes the explicit file, records v2
document/object metadata, and copies the canonical object into managed storage.

## BankBuddy CLI

Run the banking CLI with:

```bash
bankbuddy --help
bankbuddy status
bankbuddy init
```

Core command groups:

- `bankbuddy bank list|rename` manages configured bank labels.
- `bankbuddy account add|list|summary|show|update` manages configured accounts
  and display labels.
- `bankbuddy account ref add|list|remove` manages parser-visible account refs.
- `bankbuddy import --file ...` imports one supported statement.
- `bankbuddy import inbox` processes supported files from the managed inbox.
- `bankbuddy import history` inspects prior attempts.
- `bankbuddy import retry ATTEMPT_ID` retries a failed attempt.
- `bankbuddy statements summary|list` inspects imported statement inventory.
- `bankbuddy audit statements` checks statement-period coverage.
- `bankbuddy tx list` reviews transactions with filters, sorting, views,
  formats, and summaries.
- `bankbuddy category list` and `bankbuddy tx categorize` manage manual
  transaction categories.
- `bankbuddy report spending` summarizes outgoing transactions by category and
  currency.
- `bankbuddy export sqlite` writes sensitive local SQLite backups.
- `bankbuddy storage migrate-layout --dry-run|--apply` migrates legacy data
  homes into the canonical layout.

Use `--dry-run` before import and repair operations when available. Use
`--environment` before the subcommand for one-command data-home selection:

```bash
bankbuddy --environment dev status
bankbuddy --environment prod import inbox
```

## TaxBuddy CLI

Run the tax readiness CLI with:

```bash
taxbuddy --help
taxbuddy status
taxbuddy import --dry-run --file path/to/document.pdf
taxbuddy import --file path/to/document.pdf
taxbuddy import --dry-run inbox
taxbuddy import inbox
taxbuddy docs list
taxbuddy docs show 1
```

Current TaxBuddy imports are intentionally conservative. They support
text-selectable PDFs and `.txt` fixtures, detect known tax document metadata,
and fail clearly instead of guessing from filenames.
