#!/usr/bin/env bash

required_files=(
  README.md
  VERSION
  CHANGELOG.md
  CONTRIBUTING.md
  .github/pull_request_template.md
  LICENSE
  base_manifest.yaml
  Brewfile
  .github/workflows/tests.yml
  pyproject.toml
  src/bankbuddy/__init__.py
  src/bankbuddy/migrations/__init__.py
  src/bankbuddy/migrations/0001_core_schema.sql
)

for file in "${required_files[@]}"; do
  [[ -f "$file" ]] || {
    printf 'Missing required file: %s\n' "$file" >&2
    exit 1
  }
done

printf 'Repository baseline is present.\n'

if [[ -f pyproject.toml ]]; then
  uv run pytest
fi
