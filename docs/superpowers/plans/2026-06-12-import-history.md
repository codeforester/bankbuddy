# Import History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `bank-buddy import history` command so users can inspect prior import attempts without querying SQLite manually.

**Architecture:** Add a focused import-history query module that joins `import_attempts`, `import_files`, and `banks`, then convert the existing `import` command into an invoke-without-command Click group. The existing `bank-buddy import --file path/to/statement.pdf --account-id 1` path remains intact, while `bank-buddy import history` lists attempts with stable columns.

**Tech Stack:** Python 3.12, Click, SQLite, pytest, uv.

---

### Task 1: Import History Query Contract

**Files:**
- Create: `src/bankbuddy/import_history.py`
- Test: `tests/test_import_history.py`

- [x] **Step 1: Write failing tests for history rows and filters**

```python
def test_list_import_history_orders_newest_first(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    account = add_boa_account(paths)
    import_boa_csv(paths, write_csv(tmp_path, "first.csv", BOA_CSV), account_id=account.account_id)
    import_boa_csv(paths, write_csv(tmp_path, "first.csv", BOA_CSV), account_id=account.account_id)

    rows = list_import_history(paths)

    assert [row.attempt_id for row in rows] == [2, 1]
    assert rows[0].file_name == "first.csv"
    assert rows[0].status == "success"
    assert rows[0].rows_skipped_duplicate == 2
```

- [x] **Step 2: Run the focused test and confirm it fails**

Run: `uv run pytest tests/test_import_history.py -q`
Expected: import failure for missing `bankbuddy.import_history`.

- [x] **Step 3: Implement the query module**

```python
@dataclass(frozen=True)
class ImportHistoryRow:
    attempt_id: int
    file_name: str
    bank_name: str
    status: str
    started_at: str
    finished_at: str | None
    rows_parsed: int
    rows_imported: int
    rows_skipped_duplicate: int
    error_message: str | None


def list_import_history(
    paths: AppPaths,
    *,
    status: str | None = None,
    limit: int = 20,
) -> list[ImportHistoryRow]:
    initialize_database(paths)
    conditions = []
    parameters = []
    if status is not None:
        conditions.append("import_attempts.import_status = ?")
        parameters.append(status)
    parameters.append(limit)
    rows = conn.execute(
        """
        select import_attempts.attempt_id, import_files.file_name, banks.bank_name
        from import_attempts
        join import_files using (file_id)
        left join banks on banks.bank_id = import_attempts.bank_id
        order by import_attempts.attempt_id desc
        limit ?
        """,
        parameters,
    ).fetchall()
    return [
        ImportHistoryRow(
            attempt_id=int(row["attempt_id"]),
            file_name=row["file_name"],
            bank_name=row["bank_name"] or "-",
            status=row["import_status"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            rows_parsed=int(row["rows_parsed"]),
            rows_imported=int(row["rows_imported"]),
            rows_skipped_duplicate=int(row["rows_skipped_duplicate"]),
            error_message=row["error_message"],
        )
        for row in rows
    ]
```

- [x] **Step 4: Re-run focused tests and confirm they pass**

Run: `uv run pytest tests/test_import_history.py -q`
Expected: all tests pass.

### Task 2: CLI Command

**Files:**
- Modify: `src/bankbuddy/cli.py`
- Test: `tests/test_import_cli.py`

- [x] **Step 1: Write failing CLI tests**

```python
def test_import_history_outputs_attempts(tmp_path) -> None:
    seed_import_attempts(tmp_path)
    result = runner.invoke(main, ["import", "history"], env=env)

    assert result.exit_code == 0
    assert "ID  File  Bank  Status" in result.output
    assert "success" in result.output
```

- [x] **Step 2: Run the focused CLI test and confirm it fails**

Run: `uv run pytest tests/test_import_cli.py -q`
Expected: Click reports no such command or rejects the current command shape.

- [x] **Step 3: Convert `import` to a group and add `history`**

```python
@main.group("import", invoke_without_command=True)
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--account-id", type=int)
@click.pass_context
def import_command(ctx, file_path, account_id):
    if ctx.invoked_subcommand is not None:
        return
    if file_path is None or account_id is None:
        raise click.ClickException("Import requires --file and --account-id.")
    run_statement_import(ctx, file_path, account_id)


@import_command.command("history")
@click.option("--limit", type=click.IntRange(min=1), default=20, show_default=True)
@click.option("--status", type=click.Choice(["success", "failed", "partial"]))
def import_history_command(ctx, limit, status):
    rows = list_import_history(resolve_app_paths(), status=status, limit=limit)
    for row in rows:
        click.echo(
            f"{row.attempt_id}  {row.file_name}  {row.bank_name}  "
            f"{row.status}  {row.rows_parsed}  {row.rows_imported}  "
            f"{row.rows_skipped_duplicate}"
        )
```

- [x] **Step 4: Re-run focused CLI tests and confirm they pass**

Run: `uv run pytest tests/test_import_cli.py -q`
Expected: all tests pass, including existing explicit file imports.

### Task 3: Docs And Validation

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `bank_buddy_spec.md`

- [x] **Step 1: Document `import history` usage**

```bash
uv run bank-buddy import history
uv run bank-buddy import history --status success --limit 10
```

- [x] **Step 2: Run validation**

Run:

```bash
uv run pytest tests/test_import_history.py tests/test_import_cli.py -q
git diff --check
uv run pytest -q
./tests/validate.sh
```

Expected: all commands pass.

- [x] **Step 3: Commit and open PR**

```bash
git add .
git commit -m "[codex] Add import history command"
git push -u origin enhancement/26-20260612-import-history
gh pr create --repo codeforester/bankbuddy --base main --head enhancement/26-20260612-import-history --title "Add import history command"
```
