"""Storage DAO and path helpers for financial intelligence documents."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import sqlite3

from bankbuddy.financial.records import (
    DocumentObjectCreate,
    DocumentObjectRecord,
    DocumentViewCreate,
    DocumentViewRecord,
    StorageRootRecord,
)
from bankbuddy.paths import AppPaths


class FinancialStoragePathError(ValueError):
    """Raised when a storage key would escape managed storage."""


class FinancialStorageRootNotFoundError(ValueError):
    """Raised when a configured storage root code does not exist."""


class FinancialStorageDAO:
    """Persistence boundary for v2 document storage tables."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_storage_roots(self) -> list[StorageRootRecord]:
        """Return active and inactive storage roots ordered by code."""

        rows = self._conn.execute(
            """
            select
                storage_root_id,
                storage_root_code,
                root_kind,
                base_path_key,
                relative_root,
                permissions_mode,
                active
            from BB_STORAGE_ROOT
            order by storage_root_code
            """
        ).fetchall()
        return [_storage_root_from_row(row) for row in rows]

    def get_storage_root(self, storage_root_code: str) -> StorageRootRecord:
        """Return one configured storage root by code."""

        row = self._conn.execute(
            """
            select
                storage_root_id,
                storage_root_code,
                root_kind,
                base_path_key,
                relative_root,
                permissions_mode,
                active
            from BB_STORAGE_ROOT
            where storage_root_code = ?
            """,
            (storage_root_code,),
        ).fetchone()
        if row is None:
            raise FinancialStorageRootNotFoundError(
                f"Unknown financial storage root: {storage_root_code}"
            )
        return _storage_root_from_row(row)

    def create_document_object(
        self,
        record: DocumentObjectCreate,
    ) -> DocumentObjectRecord:
        """Create metadata for a canonical or managed document object."""

        object_key = validate_storage_key(record.object_key)
        root = self.get_storage_root(record.storage_root_code)
        cursor = self._conn.execute(
            """
            insert into BB_DOCUMENT_OBJECT (
                document_id,
                storage_root_id,
                object_key,
                object_role,
                content_hash,
                byte_size,
                media_type,
                original_file_name
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.document_id,
                root.storage_root_id,
                object_key,
                record.object_role,
                record.content_hash,
                record.byte_size,
                record.media_type,
                record.original_file_name,
            ),
        )
        return DocumentObjectRecord(
            document_object_id=int(cursor.lastrowid),
            storage_root_id=root.storage_root_id,
            **{**record.__dict__, "object_key": object_key},
        )

    def create_document_view(
        self,
        record: DocumentViewCreate,
    ) -> DocumentViewRecord:
        """Create metadata for a generated human-readable document view."""

        view_key = validate_storage_key(record.view_key)
        root = self.get_storage_root(record.storage_root_code)
        cursor = self._conn.execute(
            """
            insert into BB_DOCUMENT_VIEW (
                document_id,
                document_object_id,
                storage_root_id,
                view_name,
                view_key,
                materialization_kind,
                expected_hash,
                byte_size,
                status,
                last_materialized_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.document_id,
                record.document_object_id,
                root.storage_root_id,
                record.view_name,
                view_key,
                record.materialization_kind,
                record.expected_hash,
                record.byte_size,
                record.status,
                record.last_materialized_at,
            ),
        )
        return DocumentViewRecord(
            document_view_id=int(cursor.lastrowid),
            storage_root_id=root.storage_root_id,
            **{**record.__dict__, "view_key": view_key},
        )


def ensure_financial_storage_dirs(paths: AppPaths) -> None:
    """Create the v2 financial storage directories."""

    paths.financial_inbox.mkdir(parents=True, exist_ok=True)
    paths.financial_canonical.mkdir(parents=True, exist_ok=True)
    paths.financial_failed.mkdir(parents=True, exist_ok=True)
    paths.financial_duplicates.mkdir(parents=True, exist_ok=True)
    paths.financial_review.mkdir(parents=True, exist_ok=True)
    paths.financial_views.mkdir(parents=True, exist_ok=True)
    paths.financial_exports.mkdir(parents=True, exist_ok=True)


def object_key_for_hash(file_hash: str, suffix: str = "") -> str:
    """Return a deterministic canonical object key for a SHA-256 hash."""

    normalized_hash = file_hash.strip().lower()
    if len(normalized_hash) < 4:
        raise FinancialStoragePathError("Document hash must contain at least 4 chars.")
    normalized_suffix = suffix.strip().lower()
    if normalized_suffix and not normalized_suffix.startswith("."):
        normalized_suffix = f".{normalized_suffix}"
    return (
        f"sha256/{normalized_hash[:2]}/{normalized_hash[2:4]}/"
        f"{normalized_hash}{normalized_suffix}"
    )


def validate_storage_key(storage_key: str) -> str:
    """Return a normalized relative storage key or raise for unsafe input."""

    normalized_key = storage_key.strip()
    if not normalized_key:
        raise FinancialStoragePathError("Storage key cannot be empty.")
    if "\\" in normalized_key:
        raise FinancialStoragePathError("Storage key must use POSIX separators.")

    pure_path = PurePosixPath(normalized_key)
    if pure_path.is_absolute():
        raise FinancialStoragePathError("Storage key must be relative.")

    parts = pure_path.parts
    if any(part in ("", ".", "..") for part in parts):
        raise FinancialStoragePathError(
            "Storage key cannot contain empty, current, or parent path segments."
        )
    return pure_path.as_posix()


def resolve_storage_path(
    paths: AppPaths,
    storage_root: StorageRootRecord,
    storage_key: str,
) -> Path:
    """Resolve a storage root and relative key to a local filesystem path."""

    if storage_root.base_path_key != "app_root":
        raise FinancialStoragePathError(
            f"Unsupported storage base path: {storage_root.base_path_key}"
        )

    relative_root = validate_storage_key(storage_root.relative_root)
    relative_key = validate_storage_key(storage_key)
    root_path = paths.root.joinpath(*PurePosixPath(relative_root).parts)
    return root_path.joinpath(*PurePosixPath(relative_key).parts)


def protect_managed_path(path: Path) -> None:
    """Make a managed file or directory read-only as an accidental-delete guard."""

    if path.is_dir():
        path.chmod(0o555)
        return
    path.chmod(0o444)


def _storage_root_from_row(row: sqlite3.Row) -> StorageRootRecord:
    return StorageRootRecord(
        storage_root_id=int(row["storage_root_id"]),
        storage_root_code=str(row["storage_root_code"]),
        root_kind=str(row["root_kind"]),
        base_path_key=str(row["base_path_key"]),
        relative_root=str(row["relative_root"]),
        permissions_mode=str(row["permissions_mode"]),
        active=bool(row["active"]),
    )
