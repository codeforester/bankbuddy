"""Application path discovery for BankBuddy."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


BANKBUDDY_HOME_ENV = "BANKBUDDY_HOME"
BANKBUDDY_ENV_ENV = "BANKBUDDY_ENV"
DEFAULT_ENVIRONMENT = "prod"
DEFAULT_HOME_NAME = "BankBuddy"
DATABASE_NAME = "bankbuddy.sqlite3"
CANONICAL_LAYOUT = "canonical"
LEGACY_LAYOUT = "legacy"
_VALID_ENVIRONMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

AppLayout = Literal["canonical", "legacy"]
AppLayoutMode = Literal["auto", "canonical", "legacy"]


@dataclass(frozen=True)
class AppPaths:
    """Resolved local filesystem paths used by BankBuddy."""

    environment: str
    layout: AppLayout
    root: Path
    inbox: Path
    processed: Path
    duplicates: Path
    exports: Path
    tax_inbox: Path
    tax_processed: Path
    tax_duplicates: Path
    tax_exports: Path
    financial_inbox: Path
    financial_canonical: Path
    financial_failed: Path
    financial_duplicates: Path
    financial_review: Path
    financial_views: Path
    financial_exports: Path
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
    layout: AppLayoutMode = "auto",
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
    resolved_layout = _resolve_layout(resolved_root, layout)

    if resolved_layout == CANONICAL_LAYOUT:
        return AppPaths(
            environment=resolved_environment,
            layout=resolved_layout,
            root=resolved_root,
            inbox=resolved_root / "bank" / "inbox",
            processed=resolved_root / "bank" / "processed",
            duplicates=resolved_root / "bank" / "duplicates",
            exports=resolved_root / "bank" / "exports",
            tax_inbox=resolved_root / "tax" / "inbox",
            tax_processed=resolved_root / "tax" / "processed",
            tax_duplicates=resolved_root / "tax" / "duplicates",
            tax_exports=resolved_root / "tax" / "exports",
            financial_inbox=resolved_root / "financial" / "inbox",
            financial_canonical=resolved_root / "financial" / "canonical",
            financial_failed=resolved_root / "financial" / "failed",
            financial_duplicates=resolved_root / "financial" / "duplicates",
            financial_review=resolved_root / "financial" / "review",
            financial_views=resolved_root / "financial" / "views",
            financial_exports=resolved_root / "financial" / "exports",
            database=resolved_root / "database" / DATABASE_NAME,
        )

    return AppPaths(
        environment=resolved_environment,
        layout=resolved_layout,
        root=resolved_root,
        inbox=resolved_root / "inbox",
        processed=resolved_root / "processed",
        duplicates=resolved_root / "duplicates",
        exports=resolved_root / "exports",
        tax_inbox=resolved_root / "tax" / "inbox",
        tax_processed=resolved_root / "tax" / "processed",
        tax_duplicates=resolved_root / "tax" / "duplicates",
        tax_exports=resolved_root / "tax" / "exports",
        financial_inbox=resolved_root / "financial" / "inbox",
        financial_canonical=resolved_root / "financial" / "canonical",
        financial_failed=resolved_root / "financial" / "failed",
        financial_duplicates=resolved_root / "financial" / "duplicates",
        financial_review=resolved_root / "financial" / "review",
        financial_views=resolved_root / "financial" / "views",
        financial_exports=resolved_root / "financial" / "exports",
        database=resolved_root / DATABASE_NAME,
    )


def ensure_app_dirs(paths: AppPaths) -> None:
    """Create the local BankBuddy app directories."""

    paths.root.mkdir(parents=True, exist_ok=True)
    paths.database.parent.mkdir(parents=True, exist_ok=True)
    paths.inbox.mkdir(parents=True, exist_ok=True)
    paths.processed.mkdir(parents=True, exist_ok=True)
    paths.duplicates.mkdir(parents=True, exist_ok=True)
    paths.exports.mkdir(parents=True, exist_ok=True)
    paths.tax_inbox.mkdir(parents=True, exist_ok=True)
    paths.tax_processed.mkdir(parents=True, exist_ok=True)
    paths.tax_duplicates.mkdir(parents=True, exist_ok=True)
    paths.tax_exports.mkdir(parents=True, exist_ok=True)
    paths.financial_inbox.mkdir(parents=True, exist_ok=True)
    paths.financial_canonical.mkdir(parents=True, exist_ok=True)
    paths.financial_failed.mkdir(parents=True, exist_ok=True)
    paths.financial_duplicates.mkdir(parents=True, exist_ok=True)
    paths.financial_review.mkdir(parents=True, exist_ok=True)
    paths.financial_views.mkdir(parents=True, exist_ok=True)
    paths.financial_exports.mkdir(parents=True, exist_ok=True)


def _resolve_layout(root: Path, layout: AppLayoutMode) -> AppLayout:
    """Return the requested or detected BankBuddy filesystem layout."""

    if layout in (CANONICAL_LAYOUT, LEGACY_LAYOUT):
        return layout
    if layout != "auto":
        raise ValueError("BankBuddy layout must be auto, canonical, or legacy.")

    canonical_database = root / "database" / DATABASE_NAME
    canonical_bank_dir = root / "bank"
    if canonical_database.exists() or canonical_bank_dir.exists():
        return CANONICAL_LAYOUT

    legacy_markers = (
        root / DATABASE_NAME,
        root / "inbox",
        root / "processed",
        root / "duplicates",
        root / "exports",
    )
    if any(path.exists() for path in legacy_markers):
        return LEGACY_LAYOUT

    return CANONICAL_LAYOUT
