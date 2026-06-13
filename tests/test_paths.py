from bankbuddy.paths import resolve_app_paths


def test_resolve_app_paths_uses_explicit_root() -> None:
    root = "/tmp/bankbuddy-test-home"

    paths = resolve_app_paths(root)

    assert str(paths.root) == root
    assert paths.environment == "prod"
    assert str(paths.inbox) == f"{root}/inbox"
    assert str(paths.processed) == f"{root}/processed"
    assert str(paths.duplicates) == f"{root}/duplicates"
    assert str(paths.exports) == f"{root}/exports"
    assert str(paths.database) == f"{root}/bankbuddy.sqlite3"


def test_resolve_app_paths_maps_dev_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    paths = resolve_app_paths(environment="dev")

    assert paths.environment == "dev"
    assert paths.root == tmp_path / "BankBuddy-dev"
    assert paths.database == tmp_path / "BankBuddy-dev" / "bankbuddy.sqlite3"


def test_resolve_app_paths_maps_prod_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    paths = resolve_app_paths(environment="prod")

    assert paths.environment == "prod"
    assert paths.root == tmp_path / "BankBuddy"
    assert paths.database == tmp_path / "BankBuddy" / "bankbuddy.sqlite3"


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
