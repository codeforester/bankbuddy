# AI Context Directory

This directory contains AI-facing project context for BankBuddy. It is meant to
help assistants such as Claude, Codex, ChatGPT, and future AI tools orient
quickly before product, architecture, maintenance, or workflow conversations.

The files are curated Markdown, not generated truth. They summarize the current
repo and point back to canonical project sources when deeper detail is needed.

## Audience

Use this directory when an AI assistant needs to understand BankBuddy without
re-reading the whole repository. The context is suitable for upload to other AI
tools as long as it stays public-repo-safe.

## Files

- `INDEX.md` - recommended read order and file map.
- `PROJECT.md` - compact project summary and current identity.
- `ARCHITECTURE.md` - architecture, boundaries, and storage model.
- `COMMANDS.md` - `bankbuddy`, `taxbuddy`, and Base command surface.
- `WORKFLOWS.md` - contribution, validation, import, and context workflows.
- `DECISIONS.md` - durable product and architecture decisions.
- `STATUS.md` - current version, active areas, and recent changes.

## Source Of Truth

Canonical project sources remain:

- `README.md`
- `bank_buddy_spec.md`
- `CHANGELOG.md`
- `base_manifest.yaml`
- `pyproject.toml`
- `AGENTS.md`
- `CONTRIBUTING.md`
- `src/bankbuddy/`
- `tests/`

If this directory disagrees with the repo docs or code, update this directory.

## Maintenance

Update this directory when a change alters BankBuddy or TaxBuddy's product
shape, architecture, command surface, workflows, Base manifest contract, storage
model, privacy rules, release status, or durable design decisions.

Usually no update is needed for typo-only edits, formatting-only edits,
test-only changes with no product behavior impact, or internal refactors that
do not change public behavior or architecture.

## Safety

Do not put secrets, API keys, tokens, real account numbers, raw statement
contents, private local paths, personal notes, or extracted financial/tax data
in this directory. Use generic examples and point to code or docs for details.
