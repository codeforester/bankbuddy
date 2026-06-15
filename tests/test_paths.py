from bankbuddy.paths import resolve_app_paths


def test_resolve_app_paths_uses_explicit_root() -> None:
    root = "/tmp/bankbuddy-test-home"

    paths = resolve_app_paths(root)

    assert str(paths.root) == root
    assert paths.environment == "prod"
    assert paths.layout == "canonical"
    assert str(paths.inbox) == f"{root}/bank/inbox"
    assert str(paths.processed) == f"{root}/bank/processed"
    assert str(paths.duplicates) == f"{root}/bank/duplicates"
    assert str(paths.exports) == f"{root}/bank/exports"
    assert str(paths.database) == f"{root}/database/bankbuddy.sqlite3"
    assert str(paths.tax_inbox) == f"{root}/tax/inbox"
    assert str(paths.tax_processed) == f"{root}/tax/processed"
    assert str(paths.tax_duplicates) == f"{root}/tax/duplicates"
    assert str(paths.tax_exports) == f"{root}/tax/exports"


def test_resolve_app_paths_maps_dev_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    paths = resolve_app_paths(environment="dev")

    assert paths.environment == "dev"
    assert paths.root == tmp_path / "BankBuddy-dev"
    assert paths.database == (
        tmp_path / "BankBuddy-dev" / "database" / "bankbuddy.sqlite3"
    )


def test_resolve_app_paths_maps_prod_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    paths = resolve_app_paths(environment="prod")

    assert paths.environment == "prod"
    assert paths.root == tmp_path / "BankBuddy"
    assert paths.database == tmp_path / "BankBuddy" / "database" / "bankbuddy.sqlite3"


def test_resolve_app_paths_maps_named_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    paths = resolve_app_paths(environment="qa")

    assert paths.environment == "qa"
    assert paths.root == tmp_path / "BankBuddy-qa"


def test_resolve_app_paths_uses_bankbuddy_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BANKBUDDY_ENV", "dev")

    paths = resolve_app_paths()

    assert paths.environment == "dev"
    assert paths.root == tmp_path / "BankBuddy-dev"


def test_resolve_app_paths_uses_bankbuddy_home_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BANKBUDDY_ENV", "dev")
    monkeypatch.setenv("BANKBUDDY_HOME", str(tmp_path / "custom"))

    paths = resolve_app_paths()

    assert paths.environment == "dev"
    assert paths.root == tmp_path / "custom"


def test_resolve_app_paths_detects_legacy_layout(tmp_path) -> None:
    legacy_database = tmp_path / "bankbuddy.sqlite3"
    legacy_database.touch()

    paths = resolve_app_paths(tmp_path)

    assert paths.layout == "legacy"
    assert paths.database == legacy_database
    assert paths.inbox == tmp_path / "inbox"
    assert paths.processed == tmp_path / "processed"
    assert paths.duplicates == tmp_path / "duplicates"
    assert paths.exports == tmp_path / "exports"


def test_resolve_app_paths_can_force_legacy_layout(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path, layout="legacy")

    assert paths.layout == "legacy"
    assert paths.database == tmp_path / "bankbuddy.sqlite3"
