"""Tax document metadata extraction, archival, and indexing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from shutil import copy2

from bankbuddy.database import connect_database, initialize_database
from bankbuddy.import_files import canonical_file_name_with_hash
from bankbuddy.import_files import hash_file
from bankbuddy.import_files import slugify_account_ref
from bankbuddy.import_files import slugify_bank_name
from bankbuddy.imports import extract_pdf_text
from bankbuddy.paths import AppPaths


@dataclass(frozen=True)
class TaxDocumentMetadata:
    """Parser-confirmed metadata for a tax document."""

    document_type: str
    jurisdiction: str
    tax_year: int
    source_entity: str
    person_label: str | None = None
    account_ref: str | None = None


@dataclass(frozen=True)
class TaxDocumentArchivePlan:
    """Canonical archive destination for a tax document."""

    original_file_name: str
    canonical_file_name: str
    source_path: str
    processed_path: str
    metadata: TaxDocumentMetadata
    file_hash: str


@dataclass(frozen=True)
class TaxImportPlan:
    """Dry-run import plan for a tax document."""

    file_name: str
    canonical_file_name: str
    processed_path: str
    document_type: str
    jurisdiction: str
    tax_year: int
    source_entity: str
    person_label: str | None
    account_ref: str | None
    duplicate: bool
    existing_document_id: int | None


@dataclass(frozen=True)
class TaxImportSummary:
    """Result of a tax document import."""

    tax_document_id: int
    file_name: str
    canonical_file_name: str
    processed_path: str
    document_type: str
    jurisdiction: str
    tax_year: int
    source_entity: str
    person_label: str | None
    account_ref: str | None
    duplicate: bool


@dataclass(frozen=True)
class TaxDocumentRow:
    """Stored tax document metadata for list/show commands."""

    tax_document_id: int
    original_file_name: str
    canonical_file_name: str
    processed_path: str
    document_type: str
    jurisdiction: str
    tax_year: int
    source_entity: str
    person_label: str | None
    account_ref: str | None
    imported_at: str


class TaxImportFailure(ValueError):
    """Raised when a tax document cannot be imported safely."""


def parse_tax_document_text(text: str) -> TaxDocumentMetadata:
    """Extract required tax document metadata from document text."""

    document_type = _detect_document_type(text)
    jurisdiction = _detect_jurisdiction(document_type, text)
    tax_year = _detect_tax_year(text)
    source_entity = _detect_source_entity(text)
    person_label = _detect_person_label(text)
    account_ref = _detect_account_ref(text)

    if document_type is None:
        raise TaxImportFailure("Tax document is missing a supported document type.")
    if jurisdiction is None:
        raise TaxImportFailure("Tax document is missing a supported jurisdiction.")
    if tax_year is None:
        raise TaxImportFailure("Tax document is missing a tax year.")
    if source_entity is None:
        raise TaxImportFailure("Tax document is missing a source entity.")

    return TaxDocumentMetadata(
        document_type=document_type,
        jurisdiction=jurisdiction,
        tax_year=tax_year,
        source_entity=source_entity,
        person_label=person_label,
        account_ref=account_ref,
    )


def canonical_tax_document_filename(
    metadata: TaxDocumentMetadata,
    *,
    suffix: str,
) -> str:
    """Return the canonical filename for a tax document."""

    normalized_suffix = suffix.lower()
    if normalized_suffix and not normalized_suffix.startswith("."):
        normalized_suffix = f".{normalized_suffix}"

    parts = [
        str(metadata.tax_year),
        _document_type_slug(metadata.document_type),
        slugify_bank_name(metadata.source_entity),
    ]
    if metadata.person_label:
        parts.insert(0, slugify_account_ref(metadata.person_label))
    if metadata.account_ref:
        parts.append(slugify_account_ref(metadata.account_ref))
    return "_".join(parts) + normalized_suffix


def plan_tax_document_archive(
    paths: AppPaths,
    *,
    source_path: Path,
    metadata: TaxDocumentMetadata,
    file_hash: str,
) -> TaxDocumentArchivePlan:
    """Plan a canonical archive path without copying the document."""

    canonical_file_name = canonical_tax_document_filename(
        metadata,
        suffix=source_path.suffix,
    )
    relative_path = _tax_archive_relative_path(
        paths,
        metadata=metadata,
        canonical_file_name=canonical_file_name,
    )
    destination = paths.root / relative_path
    if destination.exists() and hash_file(destination) != file_hash:
        canonical_file_name = canonical_file_name_with_hash(
            canonical_file_name,
            file_hash=file_hash,
        )
        relative_path = _tax_archive_relative_path(
            paths,
            metadata=metadata,
            canonical_file_name=canonical_file_name,
        )

    return TaxDocumentArchivePlan(
        original_file_name=source_path.name,
        canonical_file_name=canonical_file_name,
        source_path=str(source_path.resolve()),
        processed_path=relative_path.as_posix(),
        metadata=metadata,
        file_hash=file_hash,
    )


def plan_tax_document_import(paths: AppPaths, source_path: Path) -> TaxImportPlan:
    """Return a dry-run tax document import plan."""

    file_hash = hash_file(source_path)
    existing = _find_tax_document_by_hash(paths, file_hash)
    if existing is not None:
        return TaxImportPlan(
            file_name=source_path.name,
            canonical_file_name=existing.canonical_file_name,
            processed_path=existing.processed_path,
            document_type=existing.document_type,
            jurisdiction=existing.jurisdiction,
            tax_year=existing.tax_year,
            source_entity=existing.source_entity,
            person_label=existing.person_label,
            account_ref=existing.account_ref,
            duplicate=True,
            existing_document_id=existing.tax_document_id,
        )

    text = extract_tax_document_text(source_path)
    metadata = parse_tax_document_text(text)
    archive = plan_tax_document_archive(
        paths,
        source_path=source_path,
        metadata=metadata,
        file_hash=file_hash,
    )
    return TaxImportPlan(
        file_name=source_path.name,
        canonical_file_name=archive.canonical_file_name,
        processed_path=archive.processed_path,
        document_type=metadata.document_type,
        jurisdiction=metadata.jurisdiction,
        tax_year=metadata.tax_year,
        source_entity=metadata.source_entity,
        person_label=metadata.person_label,
        account_ref=metadata.account_ref,
        duplicate=False,
        existing_document_id=None,
    )


def import_tax_document(paths: AppPaths, source_path: Path) -> TaxImportSummary:
    """Archive and index a tax document, idempotently by file hash."""

    initialize_database(paths)
    file_hash = hash_file(source_path)
    existing = _find_tax_document_by_hash(paths, file_hash)
    if existing is not None:
        return _summary_from_row(existing, duplicate=True)

    text = extract_tax_document_text(source_path)
    metadata = parse_tax_document_text(text)
    archive = plan_tax_document_archive(
        paths,
        source_path=source_path,
        metadata=metadata,
        file_hash=file_hash,
    )
    destination = paths.root / archive.processed_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        copy2(source_path, destination)

    with connect_database(paths) as conn:
        cursor = conn.execute(
            """
            insert into tax_documents (
                file_hash,
                original_file_name,
                canonical_file_name,
                source_path,
                processed_path,
                document_type,
                jurisdiction,
                tax_year,
                source_entity,
                person_label,
                account_ref
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_hash,
                archive.original_file_name,
                archive.canonical_file_name,
                archive.source_path,
                archive.processed_path,
                metadata.document_type,
                metadata.jurisdiction,
                metadata.tax_year,
                metadata.source_entity,
                metadata.person_label,
                metadata.account_ref,
            ),
        )
        conn.commit()
        tax_document_id = int(cursor.lastrowid)

    return TaxImportSummary(
        tax_document_id=tax_document_id,
        file_name=archive.original_file_name,
        canonical_file_name=archive.canonical_file_name,
        processed_path=archive.processed_path,
        document_type=metadata.document_type,
        jurisdiction=metadata.jurisdiction,
        tax_year=metadata.tax_year,
        source_entity=metadata.source_entity,
        person_label=metadata.person_label,
        account_ref=metadata.account_ref,
        duplicate=False,
    )


def list_tax_documents(
    paths: AppPaths,
    *,
    year: int | None = None,
    document_type: str | None = None,
) -> list[TaxDocumentRow]:
    """List indexed tax documents, newest tax year first."""

    initialize_database(paths)
    conditions: list[str] = []
    params: list[object] = []
    if year is not None:
        conditions.append("tax_year = ?")
        params.append(year)
    if document_type is not None:
        conditions.append("lower(document_type) = lower(?)")
        params.append(document_type)

    where_sql = f"where {' and '.join(conditions)}" if conditions else ""
    with connect_database(paths) as conn:
        rows = conn.execute(
            f"""
            select
                tax_document_id,
                original_file_name,
                canonical_file_name,
                processed_path,
                document_type,
                jurisdiction,
                tax_year,
                source_entity,
                person_label,
                account_ref,
                imported_at
            from tax_documents
            {where_sql}
            order by tax_year desc, tax_document_id desc
            """,
            params,
        ).fetchall()
    return [_row_from_sql(row) for row in rows]


def get_tax_document(paths: AppPaths, tax_document_id: int) -> TaxDocumentRow:
    """Return one indexed tax document."""

    initialize_database(paths)
    with connect_database(paths) as conn:
        row = conn.execute(
            """
            select
                tax_document_id,
                original_file_name,
                canonical_file_name,
                processed_path,
                document_type,
                jurisdiction,
                tax_year,
                source_entity,
                person_label,
                account_ref,
                imported_at
            from tax_documents
            where tax_document_id = ?
            """,
            (tax_document_id,),
        ).fetchone()
    if row is None:
        raise TaxImportFailure(f"Tax document not found: {tax_document_id}")
    return _row_from_sql(row)


def extract_tax_document_text(source_path: Path) -> str:
    """Extract text from a supported tax document file."""

    suffix = source_path.suffix.lower()
    if suffix == ".txt":
        return source_path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        return extract_pdf_text(source_path)
    raise TaxImportFailure(f"Unsupported tax document file type: {suffix or '(none)'}")


def _find_tax_document_by_hash(
    paths: AppPaths,
    file_hash: str,
) -> TaxDocumentRow | None:
    if not paths.database.exists():
        return None
    with connect_database(paths) as conn:
        row = conn.execute(
            """
            select
                tax_document_id,
                original_file_name,
                canonical_file_name,
                processed_path,
                document_type,
                jurisdiction,
                tax_year,
                source_entity,
                person_label,
                account_ref,
                imported_at
            from tax_documents
            where file_hash = ?
            """,
            (file_hash,),
        ).fetchone()
    if row is None:
        return None
    return _row_from_sql(row)


def _summary_from_row(row: TaxDocumentRow, *, duplicate: bool) -> TaxImportSummary:
    return TaxImportSummary(
        tax_document_id=row.tax_document_id,
        file_name=row.original_file_name,
        canonical_file_name=row.canonical_file_name,
        processed_path=row.processed_path,
        document_type=row.document_type,
        jurisdiction=row.jurisdiction,
        tax_year=row.tax_year,
        source_entity=row.source_entity,
        person_label=row.person_label,
        account_ref=row.account_ref,
        duplicate=duplicate,
    )


def _row_from_sql(row) -> TaxDocumentRow:
    return TaxDocumentRow(
        tax_document_id=row["tax_document_id"],
        original_file_name=row["original_file_name"],
        canonical_file_name=row["canonical_file_name"],
        processed_path=row["processed_path"],
        document_type=row["document_type"],
        jurisdiction=row["jurisdiction"],
        tax_year=row["tax_year"],
        source_entity=row["source_entity"],
        person_label=row["person_label"],
        account_ref=row["account_ref"],
        imported_at=row["imported_at"],
    )


def _tax_archive_relative_path(
    paths: AppPaths,
    *,
    metadata: TaxDocumentMetadata,
    canonical_file_name: str,
) -> Path:
    return Path(
        paths.tax_processed.relative_to(paths.root),
        metadata.jurisdiction.lower(),
        f"{metadata.tax_year:04d}",
        _document_type_slug(metadata.document_type),
        canonical_file_name,
    )


def _detect_document_type(text: str) -> str | None:
    upper_text = text.upper()
    if "1099-INT" in upper_text:
        return "1099-INT"
    if "1099-DIV" in upper_text:
        return "1099-DIV"
    if "1099-B" in upper_text:
        return "1099-B"
    if re.search(r"\bW-2\b", upper_text):
        return "W-2"
    if "FORM 26AS" in upper_text or "26AS" in upper_text:
        return "FORM_26AS"
    if re.search(r"\bAIS\b", upper_text):
        return "AIS"
    return None


def _detect_jurisdiction(document_type: str | None, text: str) -> str | None:
    upper_text = text.upper()
    if "JURISDICTION: US" in upper_text or document_type in {
        "1099-INT",
        "1099-DIV",
        "1099-B",
        "W-2",
    }:
        return "US"
    if "JURISDICTION: IN" in upper_text or document_type in {"FORM_26AS", "AIS"}:
        return "IN"
    return None


def _detect_tax_year(text: str) -> int | None:
    patterns = [
        r"Tax\s+Year\s*[:\-]?\s*(20\d{2})",
        r"\b(20\d{2})\s+(?:Form\s+)?(?:1099|W-2|AIS|26AS)",
        r"(?:Year|Assessment\s+Year)\s*[:\-]?\s*(20\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _detect_source_entity(text: str) -> str | None:
    for label in ("Payer", "Employer", "Issuer", "Source"):
        match = re.search(
            rf"^{label}\s*:\s*(.+)$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if match:
            value = match.group(1).strip()
            return value or None
    return None


def _detect_person_label(text: str) -> str | None:
    match = re.search(
        r"^(?:Person|Taxpayer)\s*:\s*(.+)$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _detect_account_ref(text: str) -> str | None:
    patterns = [
        r"ending\s+in\s+([0-9]{4})",
        r"Account(?:\s+number)?[^\n0-9]*([0-9]{4})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _document_type_slug(document_type: str) -> str:
    return slugify_account_ref(document_type.replace("_", "-"))
