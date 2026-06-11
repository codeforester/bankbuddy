from pathlib import Path

from bankbuddy.paths import resolve_app_paths


def test_resolve_app_paths_uses_bankbuddy_home() -> None:
    root = Path("/tmp/bankbuddy-test-home")

    paths = resolve_app_paths(root)

    assert paths.root == root
    assert paths.inbox == root / "inbox"
    assert paths.processed == root / "processed"
    assert paths.exports == root / "exports"
    assert paths.database == root / "bankbuddy.sqlite3"
