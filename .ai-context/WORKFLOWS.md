# BankBuddy Workflow Context

## Development Workflow

Use the repo guidance in `AGENTS.md` and `CONTRIBUTING.md`:

1. Create or choose a GitHub issue before implementation work.
   Prefer `basectl gh issue create` so Base adds the issue to the repo Project
   and applies `.github/base-project.yml` defaults.
2. Use one primary label: `bug`, `enhancement`, `documentation`, `ci`, or
   `security`.
3. Branch from `origin/main` with `<category>/<issue>-<YYYYMMDD>-<slug>`.
4. Use a dedicated worktree under `../bankbuddy-worktrees/<slug>` for each PR.
5. Keep the PR scoped to one issue and link it with `Fixes #<issue>` or
   `Closes #<issue>` when merge should close the issue.
6. Run the relevant narrow tests and then the project validation command.

`.github/workflows/project-intake.yml` is the fallback for issues created
through the GitHub UI, plain `gh issue create`, or external connectors. It
adds or reconciles issues into the repo-named Project on open, reopen, close,
or manual dispatch when `BASE_PROJECT_TOKEN` has Project write access.

## Validation

The project validation command is:

```bash
./tests/validate.sh
```

The Base dogfood validation path is:

```bash
basectl setup bankbuddy
basectl test bankbuddy
basectl run bankbuddy bankbuddy -- status
basectl run bankbuddy taxbuddy -- status
```

Useful narrower checks include:

```bash
uv run pytest tests/test_tax_documents.py -q
uv run pytest tests/test_imports.py -q
uv run pytest tests/test_cli.py -q
basectl repo check .
git diff --check
```

Use the narrowest relevant check first, then broaden when shared runtime,
storage, migration, parser, or CLI behavior changes.

## Import Workflow

Prefer dry-run first:

```bash
bankbuddy import --dry-run --file path/to/statement.pdf --account-id 1
bankbuddy import --dry-run inbox
taxbuddy import --dry-run --file path/to/document.pdf
taxbuddy import --dry-run inbox
```

Banking import routing should be based on document content and configured
account refs, not filenames. Explicit `--account-id` must not override a
different identity found in a document.

TaxBuddy imports should store metadata and archive the document, but not store
raw extracted tax text durably.

## Privacy Workflow

Do not commit statement files, SQLite databases, exported backups, real account
numbers, raw tax documents, extracted statement text, or user-specific data
homes. Keep examples generic.

CLI output should mask account numbers by default. Logging should avoid raw
financial document contents.

## AI Context Workflow

Update `.ai-context/` when changes affect BankBuddy or TaxBuddy's product
shape, architecture, command surface, workflows, Base manifest contract, storage
model, privacy rules, release status, or durable decisions.

Usually leave `.ai-context/` unchanged for typo-only edits, formatting-only
edits, test-only changes with no product behavior impact, or internal refactors
that do not change public behavior or architecture.
