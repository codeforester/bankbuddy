# bankbuddy

Local-first personal finance tracking.

## Development

Set up the Python environment with `uv`:

```bash
uv sync
```

Run the CLI:

```bash
uv run bank-buddy --help
uv run bank-buddy status
uv run bank-buddy init
```

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
