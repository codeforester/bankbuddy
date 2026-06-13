# Import Dry-Run Mode Implementation Plan

**Issue:** #46

**Goal:** Add `bankbuddy import --dry-run` so explicit statement imports and inbox processing can preview parser, duplicate, and archive actions without changing the database or moving files.

**Architecture:** Introduce a read-only import plan path beside the existing import persistence path. The dry-run code should reuse the same parser, account validation, transaction hashing, and canonical archive naming logic as real imports, but must not write transactions, import files, import attempts, duplicate attempts, or processed/duplicate files. Inbox dry-run should keep every source file in place and report the action that would have happened.

## Tasks

- [x] Add red CLI tests for explicit file dry-run success, duplicate-row preview, and failed parse non-persistence.
- [x] Add red inbox tests for success preview and exact duplicate preview without file/database changes.
- [x] Add read-only archive path planning helpers.
- [x] Add read-only Bank of America CSV/PDF import planning helpers.
- [x] Thread `dry_run` through `bankbuddy import` and `bankbuddy import inbox` output.
- [x] Update README/spec/changelog notes for the new command behavior.
- [x] Run focused and full validation.
