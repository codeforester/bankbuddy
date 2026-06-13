"""Application path discovery for BankBuddy."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


BANKBUDDY_HOME_ENV = "BANKBUDDY_HOME"
BANKBUDDY_ENV_ENV = "BANKBUDDY_ENV"
DEFAULT_ENVIRONMENT = "prod"
DEFAULT_HOME_NAME = "BankBuddy"
DATABASE_NAME = "bankbuddy.sqlite3"
_VALID_ENVIRONMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class AppPaths:
    """Resolved local filesystem paths used by BankBuddy."""

    environment: str
    root: Path
    inbox: Path
    processed: Path
    duplicates: Path
    exports: Path
    database: Path


def normalize_environment(value: str | None = None) -> str:
    """Return a canonical BankBuddy environment name."""

    if value is None:
        return DEFAULT_ENVIRONMENT
    normalized = str(value).strip().lower()
    if not normalized:
        return DEFAULT_ENVIRONMENT
    if not _VALID_ENVIRONMENT_RE.match(normalized):
        raise ValueError(
            "BankBuddy environment must start with a letter or digit and contain "
            "only letters, digits, dot, underscore, and dash."
        )
    return normalized


def default_app_home(environment: str | None = None) -> Path:
    """Return the default BankBuddy home directory for an environment."""

    normalized_environment = normalize_environment(environment)
    if normalized_environment == "prod":
        return Path.home() / DEFAULT_HOME_NAME
    return Path.home() / f"{DEFAULT_HOME_NAME}-{normalized_environment}"


def resolve_app_paths(
    root: Path | str | None = None,
    *,
    environment: str | None = None,
) -> AppPaths:
    """Resolve the BankBuddy app directory layout."""

    resolved_environment = normalize_environment(
        environment or os.environ.get(BANKBUDDY_ENV_ENV)
    )
    if root is None:
        root = os.environ.get(BANKBUDDY_HOME_ENV)
    resolved_root = (
        Path(root).expanduser() if root else default_app_home(resolved_environment)
    )

    return AppPaths(
        environment=resolved_environment,
        root=resolved_root,
        inbox=resolved_root / "inbox",
        processed=resolved_root / "processed",
        duplicates=resolved_root / "duplicates",
        exports=resolved_root / "exports",
        database=resolved_root / DATABASE_NAME,
    )


def ensure_app_dirs(paths: AppPaths) -> None:
    """Create the local BankBuddy app directories."""

    paths.root.mkdir(parents=True, exist_ok=True)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    paths.processed.mkdir(parents=True, exist_ok=True)
    paths.duplicates.mkdir(parents=True, exist_ok=True)
    paths.exports.mkdir(parents=True, exist_ok=True)
