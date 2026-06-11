"""Application path discovery for BankBuddy."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BANKBUDDY_HOME_ENV = "BANKBUDDY_HOME"
DEFAULT_HOME_NAME = "BankBuddy"
DATABASE_NAME = "bankbuddy.sqlite3"


@dataclass(frozen=True)
class AppPaths:
    """Resolved local filesystem paths used by BankBuddy."""

    root: Path
    inbox: Path
    processed: Path
    exports: Path
    database: Path


def default_app_home() -> Path:
    """Return the default BankBuddy home directory."""

    return Path.home() / DEFAULT_HOME_NAME


def resolve_app_paths(root: Path | str | None = None) -> AppPaths:
    """Resolve the BankBuddy app directory layout."""

    if root is None:
        root = os.environ.get(BANKBUDDY_HOME_ENV)
    resolved_root = Path(root).expanduser() if root else default_app_home()

    return AppPaths(
        root=resolved_root,
        inbox=resolved_root / "inbox",
        processed=resolved_root / "processed",
        exports=resolved_root / "exports",
        database=resolved_root / DATABASE_NAME,
    )


def ensure_app_dirs(paths: AppPaths) -> None:
    """Create the local BankBuddy app directories."""

    paths.root.mkdir(parents=True, exist_ok=True)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    paths.processed.mkdir(parents=True, exist_ok=True)
    paths.exports.mkdir(parents=True, exist_ok=True)
