# Agent Instructions for bankbuddy

Use this file for repository-local agent guidance. User instructions still take
precedence over this baseline.

## Workflow

1. Create or choose a GitHub issue before implementation work.
   Prefer `basectl gh issue create` over plain `gh issue create` so Base can
   add the issue to the repo-named GitHub Project and apply
   `.github/base-project.yml` defaults immediately.
2. Use one standard issue label: `bug`, `enhancement`, `documentation`,
   `ci`, or `security`.
3. Branch from the issue with:

   ```text
   <category>/<issue>-<YYYYMMDD>-<slug>
   ```

4. Use a dedicated worktree for each pull request:

   ```bash
   git fetch origin
   git worktree add -b <branch> ../bankbuddy-worktrees/<slug> origin/main
   ```

5. Keep the pull request scoped to the issue and link it with
   `Fixes #<issue>` or `Closes #<issue>` when merge should close the issue.
6. Preserve existing user changes. Do not overwrite project-owned files unless
   the user explicitly asks for that edit.

If an issue is created through the GitHub UI, plain `gh issue create`, or an
external connector, the Project Intake workflow should add it to the repo
Project. If Project fields still look wrong, run `basectl repo configure` or
`basectl gh project issue set-fields` to reconcile the item before starting
implementation.

The Project Intake workflow needs a `BASE_PROJECT_TOKEN` Actions secret with
GitHub Project write access when the default `GITHUB_TOKEN` cannot update the
user-owned Project. Keep that token in GitHub Actions secrets, not in the repo.

## Validation

Run the project validation command before publishing changes:

   ```bash
   ./tests/validate.sh
   ```

Also run narrower tests for the files changed when available.

## Documentation

Update docs when behavior, commands, setup, or workflow expectations change.
Update `CHANGELOG.md` only for notable user-visible or release-worthy changes.

## AI Context Maintenance

Treat `.ai-context/` as the AI-facing orientation layer for BankBuddy and
TaxBuddy. Update it when a change affects the product shape, architecture,
command surface, workflows, Base manifest contract, storage model, privacy
rules, release status, or durable design decisions.

Usually leave `.ai-context/` unchanged for typo-only edits, formatting-only
edits, test-only changes with no product behavior impact, or internal refactors
that do not change public behavior or architecture.

Keep `.ai-context/` safe to share with other AI tools: no secrets, API keys,
tokens, real account numbers, raw statement contents, private local paths, or
personal notes. Canonical docs and code remain the source of truth; update
`.ai-context/` when it drifts.

## Finish

After merge, sync main, remove the worktree, and delete merged local
and remote branches when safe.
