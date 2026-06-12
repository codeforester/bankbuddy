"""Helpers for imported statement file metadata and archiving."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
import re
from shutil import copy2

from bankbuddy.paths import AppPaths


@dataclass(frozen=True)
class ImportFileMetadata:
    """File metadata stored after a successful import."""

    original_file_name: str
    canonical_file_name: str
    source_path: str
    processed_path: str
    statement_start_date: str
    statement_end_date: str
    account_ref: str
    source_format: str


def canonical_statement_filename(
    *,
    bank_name: str,
    account_ref: str,
    statement_start_date: str,
    statement_end_date: str,
    suffix: str,
) -> str:
    """Return the canonical statement filename for parser-confirmed metadata."""

    normalized_suffix = suffix.lower()
    if normalized_suffix and not normalized_suffix.startswith("."):
        normalized_suffix = f".{normalized_suffix}"

    return (
        f"{slugify_bank_name(bank_name)}_{slugify_account_ref(account_ref)}_"
        f"{statement_start_date}_{statement_end_date}{normalized_suffix}"
    )


def import_archive_relative_path(
    *,
    bank_name: str,
    statement_end_date: str,
    canonical_file_name: str,
) -> Path:
    """Return the archive path relative to the BankBuddy home directory."""

    period_end = date.fromisoformat(statement_end_date)
    return Path(
        "processed",
        slugify_bank_name(bank_name),
        f"{period_end.year:04d}",
        f"{period_end.month:02d}",
        canonical_file_name,
    )


def archive_statement_file(
    paths: AppPaths,
    *,
    source_path: Path,
    bank_name: str,
    account_ref: str,
    statement_start_date: str,
    statement_end_date: str,
    source_format: str,
    file_hash: str,
) -> ImportFileMetadata:
    """Copy an imported statement into BankBuddy-managed processed storage."""

    canonical_file_name = canonical_statement_filename(
        bank_name=bank_name,
        account_ref=account_ref,
        statement_start_date=statement_start_date,
        statement_end_date=statement_end_date,
        suffix=source_path.suffix,
    )
    relative_path = import_archive_relative_path(
        bank_name=bank_name,
        statement_end_date=statement_end_date,
        canonical_file_name=canonical_file_name,
    )
    destination = paths.root / relative_path
    if destination.exists() and hash_file(destination) != file_hash:
        canonical_file_name = canonical_file_name_with_hash(
            canonical_file_name,
            file_hash=file_hash,
        )
        relative_path = import_archive_relative_path(
            bank_name=bank_name,
            statement_end_date=statement_end_date,
            canonical_file_name=canonical_file_name,
        )
        destination = paths.root / relative_path

    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy2(source_path, destination)

    return ImportFileMetadata(
        original_file_name=source_path.name,
        canonical_file_name=canonical_file_name,
        source_path=str(source_path.resolve()),
        processed_path=relative_path.as_posix(),
        statement_start_date=statement_start_date,
        statement_end_date=statement_end_date,
        account_ref=slugify_account_ref(account_ref),
        source_format=source_format,
    )


def canonical_file_name_with_hash(canonical_file_name: str, *, file_hash: str) -> str:
    """Add a short hash suffix before the extension for archive collisions."""

    path = Path(canonical_file_name)
    return f"{path.stem}-{file_hash[:8]}{path.suffix}"


def slugify_bank_name(bank_name: str) -> str:
    """Return a lowercase filesystem-safe bank slug."""

    slug = re.sub(r"[^a-z0-9]+", "-", bank_name.lower()).strip("-")
    return slug or "unknown-bank"


def slugify_account_ref(account_ref: str) -> str:
    """Return a filesystem-safe account reference."""

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", account_ref).strip("-")
    return slug.lower() or "unknown-account"


def hash_file(path: Path) -> str:
    """Return the SHA-256 hash for a file."""

    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
