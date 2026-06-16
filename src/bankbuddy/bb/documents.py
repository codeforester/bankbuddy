"""Generic document import services for the BankBuddy v2 model."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import mimetypes
from pathlib import Path
import shutil

from bankbuddy.bb.dao import FinancialIntelligenceDAO
from bankbuddy.bb.records import DocumentCreate
from bankbuddy.bb.records import DocumentListFilter
from bankbuddy.bb.records import DocumentMetadataUpdate
from bankbuddy.bb.records import DocumentObjectCreate
from bankbuddy.bb.records import DocumentObjectRecord
from bankbuddy.bb.records import DocumentRecord
from bankbuddy.bb.storage import FinancialStorageDAO
from bankbuddy.bb.storage import object_key_for_hash
from bankbuddy.bb.storage import protect_managed_path
from bankbuddy.bb.storage import resolve_storage_path
from bankbuddy.database import connect_database
from bankbuddy.database import initialize_database
from bankbuddy.paths import AppPaths


DOCUMENT_STATUSES = ("active", "archived", "duplicate", "failed")


@dataclass(frozen=True)
class DocumentImportPlan:
    """Dry-run-safe plan for importing one document."""

    source_path: Path
    file_hash: str
    byte_size: int
    media_type: str
    object_key: str
    canonical_relative_path: str


@dataclass(frozen=True)
class DocumentImportResult:
    """Result of importing one document into v2 storage."""

    plan: DocumentImportPlan
    document: DocumentRecord
    document_object: DocumentObjectRecord
    duplicate: bool


@dataclass(frozen=True)
class DocumentSummary:
    """Read-only document summary with canonical object metadata."""

    document: DocumentRecord
    canonical_object: DocumentObjectRecord | None


class DocumentImportError(ValueError):
    """Raised when a generic document import cannot be planned or completed."""


class DocumentMetadataError(ValueError):
    """Raised when document metadata cannot be updated."""


def plan_document_import(paths: AppPaths, source_path: Path) -> DocumentImportPlan:
    """Return a deterministic import plan without creating directories or rows."""

    resolved_source = source_path.expanduser()
    if not resolved_source.is_file():
        raise DocumentImportError(f"Document file does not exist: {resolved_source}")

    file_hash = hash_file(resolved_source)
    object_key = object_key_for_hash(file_hash, resolved_source.suffix)
    return DocumentImportPlan(
        source_path=resolved_source,
        file_hash=file_hash,
        byte_size=resolved_source.stat().st_size,
        media_type=guess_media_type(resolved_source),
        object_key=object_key,
        canonical_relative_path=f"financial/canonical/{object_key}",
    )


def import_document(paths: AppPaths, source_path: Path) -> DocumentImportResult:
    """Import one document into the v2 canonical object store."""

    plan = plan_document_import(paths, source_path)
    initialize_database(paths)

    with connect_database(paths) as conn:
        documents = FinancialIntelligenceDAO(conn)
        storage = FinancialStorageDAO(conn)
        document = documents.find_document_by_hash(plan.file_hash)
        document_existed = document is not None
        if document is None:
            document = documents.create_document(
                DocumentCreate(
                    file_hash=plan.file_hash,
                    original_file_name=plan.source_path.name,
                )
            )

        document_object = storage.find_document_object(
            storage_root_code="FINANCIAL_CANONICAL",
            object_key=plan.object_key,
        )
        object_existed = document_object is not None
        canonical_root = storage.get_storage_root("FINANCIAL_CANONICAL")
        canonical_path = resolve_storage_path(paths, canonical_root, plan.object_key)

        if document_object is None:
            _copy_canonical_object(plan.source_path, canonical_path, plan.file_hash)
            document_object = storage.create_document_object(
                DocumentObjectCreate(
                    document_id=document.document_id,
                    storage_root_code="FINANCIAL_CANONICAL",
                    object_key=plan.object_key,
                    object_role="canonical",
                    content_hash=plan.file_hash,
                    byte_size=plan.byte_size,
                    media_type=plan.media_type,
                    original_file_name=plan.source_path.name,
                )
            )
        elif not canonical_path.exists():
            _copy_canonical_object(plan.source_path, canonical_path, plan.file_hash)
        elif hash_file(canonical_path) != plan.file_hash:
            raise DocumentImportError(
                f"Canonical object content mismatch: {plan.canonical_relative_path}"
            )

        conn.commit()

    return DocumentImportResult(
        plan=plan,
        document=document,
        document_object=document_object,
        duplicate=document_existed and object_existed,
    )


def list_documents(
    paths: AppPaths,
    *,
    document_type: str | None = None,
    jurisdiction_code: str | None = None,
    tax_year: int | None = None,
    document_status: str | None = None,
) -> list[DocumentSummary]:
    """Return imported v2 documents with canonical object metadata."""

    if not paths.database.exists():
        return []

    filters = DocumentListFilter(
        document_type=_clean_text(document_type),
        jurisdiction_code=_clean_jurisdiction_code(jurisdiction_code),
        tax_year=tax_year,
        document_status=document_status,
    )
    with connect_database(paths) as conn:
        documents = FinancialIntelligenceDAO(conn)
        storage = FinancialStorageDAO(conn)
        return [
            DocumentSummary(
                document=document,
                canonical_object=storage.find_canonical_document_object(
                    document.document_id
                ),
            )
            for document in documents.list_documents(filters)
        ]


def get_document_summary(paths: AppPaths, document_id: int) -> DocumentSummary | None:
    """Return one imported v2 document with canonical object metadata."""

    if not paths.database.exists():
        return None

    with connect_database(paths) as conn:
        documents = FinancialIntelligenceDAO(conn)
        storage = FinancialStorageDAO(conn)
        document = documents.get_document(document_id)
        if document is None:
            return None
        return DocumentSummary(
            document=document,
            canonical_object=storage.find_canonical_document_object(document_id),
        )


def update_document_metadata(
    paths: AppPaths,
    document_id: int,
    *,
    document_type: str | None = None,
    jurisdiction_code: str | None = None,
    tax_year: int | None = None,
    document_status: str | None = None,
) -> DocumentSummary | None:
    """Update one document's user-editable metadata."""

    update = _build_metadata_update(
        document_type=document_type,
        jurisdiction_code=jurisdiction_code,
        tax_year=tax_year,
        document_status=document_status,
    )
    if not paths.database.exists():
        return None

    with connect_database(paths) as conn:
        documents = FinancialIntelligenceDAO(conn)
        storage = FinancialStorageDAO(conn)
        if (
            update.jurisdiction_code is not None
            and not documents.jurisdiction_exists(update.jurisdiction_code)
        ):
            raise DocumentMetadataError(
                f"Unknown jurisdiction code: {update.jurisdiction_code}"
            )
        document = documents.update_document_metadata(document_id, update)
        if document is None:
            return None
        conn.commit()
        return DocumentSummary(
            document=document,
            canonical_object=storage.find_canonical_document_object(document_id),
        )


def hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest for a local file."""

    digest = sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def guess_media_type(path: Path) -> str:
    """Return a stable media type for a local document path."""

    media_type, _ = mimetypes.guess_type(path.name)
    return media_type or "application/octet-stream"


def _build_metadata_update(
    *,
    document_type: str | None,
    jurisdiction_code: str | None,
    tax_year: int | None,
    document_status: str | None,
) -> DocumentMetadataUpdate:
    normalized_type = _clean_text(document_type)
    normalized_jurisdiction = _clean_jurisdiction_code(jurisdiction_code)
    normalized_status = _clean_text(document_status)
    if normalized_status is not None and normalized_status not in DOCUMENT_STATUSES:
        raise DocumentMetadataError(f"Unknown document status: {normalized_status}")
    if tax_year is not None and (tax_year < 1000 or tax_year > 9999):
        raise DocumentMetadataError("Tax year must be a four-digit year.")
    if all(
        value is None
        for value in (
            normalized_type,
            normalized_jurisdiction,
            tax_year,
            normalized_status,
        )
    ):
        raise DocumentMetadataError("At least one metadata option is required.")
    return DocumentMetadataUpdate(
        document_type=normalized_type,
        jurisdiction_code=normalized_jurisdiction,
        tax_year=tax_year,
        document_status=normalized_status,
    )


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned


def _clean_jurisdiction_code(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    return cleaned.upper()


def _copy_canonical_object(source_path: Path, canonical_path: Path, file_hash: str) -> None:
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, canonical_path)
    if hash_file(canonical_path) != file_hash:
        canonical_path.unlink(missing_ok=True)
        raise DocumentImportError(
            f"Copied document hash did not match source: {source_path.name}"
        )
    protect_managed_path(canonical_path)
