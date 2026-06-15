#!/usr/bin/env bash

required_files=(
  README.md
  VERSION
  CHANGELOG.md
  CONTRIBUTING.md
  .github/pull_request_template.md
  .github/base-project.yml
  LICENSE
  base_manifest.yaml
  Brewfile
  .github/workflows/project-intake.yml
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

for default in \
  "status: Backlog" \
  "priority: P2" \
  "area: Product" \
  "initiative: Adoption Polish" \
  "size: S"
do
  grep -Fq "$default" .github/base-project.yml || {
    printf 'Missing Project issue default: %s\n' "$default" >&2
    exit 1
  }
done

grep -Fq "BASE_PROJECT_TOKEN" .github/workflows/project-intake.yml || {
  printf 'Project intake workflow must use BASE_PROJECT_TOKEN fallback.\n' >&2
  exit 1
}

if [[ -f pyproject.toml ]]; then
  uv run pytest
fi
