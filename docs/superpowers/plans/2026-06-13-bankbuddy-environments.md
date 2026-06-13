# BankBuddy Environments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class BankBuddy data environments selected by `BANKBUDDY_ENV`, visible in `status`, and exported during Base activation.

**Architecture:** Keep `BANKBUDDY_HOME` as the explicit data-home override. Add environment resolution to `bankbuddy.runtime`, data-home mapping to `bankbuddy.paths`, and pass the runtime into path resolution from the CLI. Add `.base/activate.sh` so activated project shells expose `BANKBUDDY_ENV` without freezing `BANKBUDDY_HOME`.

**Tech Stack:** Python 3.12, Click, pytest, uv, Base `activate.source`.

---

### Task 1: Resolve Data Environment And Paths

**Files:**
- Modify: `src/bankbuddy/runtime.py`
- Modify: `src/bankbuddy/paths.py`
- Test: `tests/test_paths.py`
- Test: `tests/test_cli.py`

- [x] **Step 1: Write failing tests**

Add tests that prove:

```python
def test_resolve_app_paths_maps_dev_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    paths = resolve_app_paths(environment="dev")
    assert paths.environment == "dev"
    assert paths.root == tmp_path / "BankBuddy-dev"


def test_resolve_app_paths_maps_prod_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    paths = resolve_app_paths(environment="prod")
    assert paths.environment == "prod"
    assert paths.root == tmp_path / "BankBuddy"


def test_resolve_app_paths_honors_bankbuddy_home_override(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKBUDDY_HOME", str(tmp_path / "custom"))
    paths = resolve_app_paths(environment="dev")
    assert paths.environment == "dev"
    assert paths.root == tmp_path / "custom"
```

Also update CLI status tests to expect `Environment:` and `Data home:`.

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_paths.py tests/test_cli.py -q
```

Expected: fail because `AppPaths.environment`, environment path mapping, and status output do not exist yet.

- [x] **Step 3: Implement environment resolution**

Add `BANKBUDDY_ENV`, environment normalization, and environment-to-home mapping. Use precedence:

```text
BANKBUDDY_HOME for data home override
CLI --environment for command environment
BANKBUDDY_ENV for session environment
config environment
prod default
```

- [x] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_paths.py tests/test_cli.py -q
```

Expected: pass.

### Task 2: Export Session Environment During Activation

**Files:**
- Create: `.base/activate.sh`
- Modify: `base_manifest.yaml`
- Test: `tests/test_base_activation.py`

- [x] **Step 1: Write failing tests**

Add tests that parse `base_manifest.yaml` and execute `.base/activate.sh` in Bash:

```python
def test_base_manifest_sources_bankbuddy_activation_script():
    assert ".base/activate.sh" in manifest["activate"]["source"]


def test_activation_script_defaults_bankbuddy_env_to_dev():
    assert run_script({}).stdout.strip() == "dev"


def test_activation_script_preserves_existing_bankbuddy_env():
    assert run_script({"BANKBUDDY_ENV": "prod"}).stdout.strip() == "prod"
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_base_activation.py -q
```

Expected: fail because the activation script and manifest entry do not exist.

- [x] **Step 3: Add activation script and manifest source**

Create `.base/activate.sh`:

```bash
#!/usr/bin/env bash

if [[ -z "${BANKBUDDY_ENV:-}" ]]; then
    export BANKBUDDY_ENV=dev
fi
```

Update `base_manifest.yaml`:

```yaml
activate:
  source:
    - .base/activate.sh
```

- [x] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_base_activation.py -q
```

Expected: pass.

### Task 3: Documentation And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `bank_buddy_spec.md`
- Modify: `CHANGELOG.md`

- [x] **Step 1: Update docs**

Document session switching:

```bash
BANKBUDDY_ENV=dev basectl activate bankbuddy
bankbuddy status
export BANKBUDDY_ENV=prod
bankbuddy status
```

Explain that `BANKBUDDY_HOME` points at the data home and overrides the mapped environment path.

- [x] **Step 2: Run final checks**

Run:

```bash
uv run pytest
git diff --check
./tests/validate.sh
uv lock --check
```

Expected: all pass.

- [ ] **Step 3: Commit and PR**

Commit:

```bash
git add .
git commit -m "Add BankBuddy data environments"
```

Open a PR that closes issue #41.
