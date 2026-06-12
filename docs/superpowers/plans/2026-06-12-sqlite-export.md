# SQLite Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `bank-buddy export sqlite --output FILE` so users can create an explicit SQLite backup/export of their local BankBuddy database.

**Architecture:** Add a focused `bankbuddy.exports` module with `export_sqlite_database(paths, output_path, force=False)`. The module initializes the database, validates the destination, refuses accidental overwrites, and uses SQLite's backup API to write the export. Add a Click `export sqlite` command that reports the destination and prints a sensitive-data warning.

**Tech Stack:** Python 3.12, Click, SQLite, pytest, uv.

---

### Task 1: SQLite Export Service

**Files:**
- Create: `src/bankbuddy/exports.py`
- Test: `tests/test_exports.py`

- [x] **Step 1: Write failing export service tests**

Create `tests/test_exports.py`:

```python
import sqlite3

import pytest

from bankbuddy.database import initialize_database
from bankbuddy.exports import ExportFailure
from bankbuddy.exports import export_sqlite_database
from bankbuddy.paths import resolve_app_paths


def test_export_sqlite_database_writes_backup_file(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    initialize_database(paths)
    output_path = tmp_path / "backup.sqlite3"

    result = export_sqlite_database(paths, output_path)

    assert result == output_path
    assert output_path.is_file()
    with sqlite3.connect(output_path) as conn:
        row = conn.execute(
            "select name from sqlite_master where type = 'table' and name = ?",
            ("schema_migrations",),
        ).fetchone()
    assert row == ("schema_migrations",)


def test_export_sqlite_database_refuses_existing_file_without_force(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    output_path = tmp_path / "backup.sqlite3"
    output_path.write_text("do not replace", encoding="utf-8")

    with pytest.raises(ExportFailure, match="already exists"):
        export_sqlite_database(paths, output_path)

    assert output_path.read_text(encoding="utf-8") == "do not replace"


def test_export_sqlite_database_force_overwrites_existing_file(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    output_path = tmp_path / "backup.sqlite3"
    output_path.write_text("replace me", encoding="utf-8")

    export_sqlite_database(paths, output_path, force=True)

    with sqlite3.connect(output_path) as conn:
        row = conn.execute(
            "select name from sqlite_master where type = 'table' and name = ?",
            ("schema_migrations",),
        ).fetchone()
    assert row == ("schema_migrations",)


def test_export_sqlite_database_requires_existing_parent(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    output_path = tmp_path / "missing" / "backup.sqlite3"

    with pytest.raises(ExportFailure, match="parent directory does not exist"):
        export_sqlite_database(paths, output_path)


def test_export_sqlite_database_refuses_source_database_path(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    initialize_database(paths)

    with pytest.raises(ExportFailure, match="cannot be the live database"):
        export_sqlite_database(paths, paths.database, force=True)
```

- [x] **Step 2: Run focused tests and confirm they fail**

Run: `uv run pytest tests/test_exports.py -q`

Expected: import failure because `bankbuddy.exports` does not exist.

- [x] **Step 3: Implement the export service**

Create `src/bankbuddy/exports.py`:

```python
from __future__ import annotations

from pathlib import Path
import sqlite3

from bankbuddy.database import initialize_database
from bankbuddy.paths import AppPaths


class ExportFailure(ValueError):
    """Raised when a database export cannot proceed."""


def export_sqlite_database(
    paths: AppPaths,
    output_path: Path,
    *,
    force: bool = False,
) -> Path:
    initialize_database(paths)
    resolved_output = output_path.expanduser().resolve()
    resolved_database = paths.database.expanduser().resolve()

    if resolved_output == resolved_database:
        raise ExportFailure("Export output cannot be the live database path.")
    if not resolved_output.parent.is_dir():
        raise ExportFailure(
            f"Export parent directory does not exist: {resolved_output.parent}"
        )
    if resolved_output.is_dir():
        raise ExportFailure(f"Export output is a directory: {resolved_output}")
    if resolved_output.exists():
        if not force:
            raise ExportFailure(
                f"Export output already exists: {resolved_output}. Use --force to overwrite."
            )
        resolved_output.unlink()

    with sqlite3.connect(resolved_database) as source:
        with sqlite3.connect(resolved_output) as destination:
            source.backup(destination)

    return resolved_output
```

- [x] **Step 4: Re-run focused tests and confirm they pass**

Run: `uv run pytest tests/test_exports.py -q`

Expected: all export service tests pass.

### Task 2: Export CLI

**Files:**
- Modify: `src/bankbuddy/cli.py`
- Test: `tests/test_export_cli.py`

- [x] **Step 1: Write failing CLI tests**

Create `tests/test_export_cli.py`:

```python
import sqlite3

from click.testing import CliRunner

from bankbuddy.cli import main


def test_export_sqlite_command_writes_database_and_warning(tmp_path) -> None:
    output_path = tmp_path / "backup.sqlite3"

    result = CliRunner().invoke(
        main,
        ["export", "sqlite", "--output", str(output_path)],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert f"Exported SQLite database to {output_path}" in result.output
    assert "contains sensitive financial data and actual account numbers" in result.output
    with sqlite3.connect(output_path) as conn:
        row = conn.execute(
            "select name from sqlite_master where type = 'table' and name = ?",
            ("schema_migrations",),
        ).fetchone()
    assert row == ("schema_migrations",)


def test_export_sqlite_command_refuses_existing_output_without_force(tmp_path) -> None:
    output_path = tmp_path / "backup.sqlite3"
    output_path.write_text("do not overwrite", encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["export", "sqlite", "--output", str(output_path)],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "already exists" in result.output
    assert output_path.read_text(encoding="utf-8") == "do not overwrite"


def test_export_sqlite_command_force_overwrites_existing_output(tmp_path) -> None:
    output_path = tmp_path / "backup.sqlite3"
    output_path.write_text("overwrite", encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["export", "sqlite", "--output", str(output_path), "--force"],
        env={"BANKBUDDY_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    with sqlite3.connect(output_path) as conn:
        row = conn.execute(
            "select name from sqlite_master where type = 'table' and name = ?",
            ("schema_migrations",),
        ).fetchone()
    assert row == ("schema_migrations",)
```

- [x] **Step 2: Run focused CLI tests and confirm they fail**

Run: `uv run pytest tests/test_export_cli.py -q`

Expected: Click reports no `export` command.

- [x] **Step 3: Implement the CLI group and sqlite subcommand**

Modify `src/bankbuddy/cli.py`:
- Import `ExportFailure` and `export_sqlite_database`.
- Add `@main.group("export")`.
- Add `export sqlite --output FILE [--force]`.
- Use `click.ClickException` for `ExportFailure`.
- Echo the exported path and sensitive-data warning on success.

- [x] **Step 4: Re-run focused CLI tests and confirm they pass**

Run: `uv run pytest tests/test_export_cli.py -q`

Expected: all export CLI tests pass.

### Task 3: Docs And Validation

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`
- Modify: `docs/superpowers/plans/2026-06-12-sqlite-export.md`

- [x] **Step 1: Document export usage**

Add examples:

```bash
uv run bank-buddy export sqlite --output ~/Desktop/bankbuddy-backup.sqlite3
uv run bank-buddy export sqlite --output ~/Desktop/bankbuddy-backup.sqlite3 --force
```

Update the design spec changelog and durability section to note overwrite protection and the sensitive-data warning.

- [x] **Step 2: Run final validation**

Run:

```bash
uv run pytest -q
./tests/validate.sh
git diff --check
```

Expected: all commands pass.

- [ ] **Step 3: Commit and open PR**

```bash
git add .
git commit -m "[codex] Add SQLite export command"
git push -u origin enhancement/31-20260612-sqlite-export
gh pr create --repo codeforester/bankbuddy --base main --head enhancement/31-20260612-sqlite-export --title "Add SQLite export command"
```
