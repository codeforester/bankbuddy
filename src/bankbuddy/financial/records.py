"""Typed records used by financial intelligence DAOs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceTypeRecord:
    """A seeded reference/type row."""

    type_id: int
    code: str
    display_name: str
    value_kind: str | None = None
    sensitivity: str | None = None
    is_system: bool = True


@dataclass(frozen=True)
class EntityAttributeTypeRecord:
    """A typed entity attribute definition."""

    entity_attribute_type_id: int
    attribute_code: str
    display_name: str
    value_kind: str
    sensitivity: str
    is_system: bool


@dataclass(frozen=True)
class RelationshipTypeRecord:
    """A typed relationship definition."""

    relationship_type_id: int
    relationship_type_code: str
    display_name: str
    is_system: bool


@dataclass(frozen=True)
class ObservationTypeRecord:
    """A typed observation definition."""

    observation_type_id: int
    observation_type_code: str
    display_name: str
    value_kind: str
    is_system: bool


@dataclass(frozen=True)
class DocumentCreate:
    """Input data for creating a v2 document record."""

    file_hash: str
    original_file_name: str
    canonical_file_name: str | None = None
    storage_path: str | None = None
    source_uri: str | None = None
    document_type: str | None = None
    jurisdiction_code: str | None = None
    tax_year: int | None = None
    document_status: str = "active"


@dataclass(frozen=True)
class DocumentRecord(DocumentCreate):
    """Stored v2 document record."""

    document_id: int = 0


@dataclass(frozen=True)
class EntityCreate:
    """Input data for creating a v2 entity record."""

    entity_type: str
    display_name: str | None = None
    status: str = "active"


@dataclass(frozen=True)
class EntityRecord(EntityCreate):
    """Stored v2 entity record."""

    entity_id: int = 0


@dataclass(frozen=True)
class EntityAttributeCreate:
    """Input data for creating a typed entity attribute."""

    entity_id: int
    attribute_type_code: str
    value_text: str | None = None
    value_integer: int | None = None
    value_decimal: str | None = None
    value_date: str | None = None
    value_boolean: bool | None = None
    source_document_id: int | None = None
    valid_from: str | None = None
    valid_to: str | None = None


@dataclass(frozen=True)
class EntityAttributeRecord(EntityAttributeCreate):
    """Stored typed entity attribute."""

    entity_attribute_id: int = 0
    entity_attribute_type_id: int = 0


@dataclass(frozen=True)
class ObservationCreate:
    """Input data for creating a typed observation."""

    observation_type_code: str
    document_id: int | None = None
    subject_entity_id: int | None = None
    value_text: str | None = None
    value_integer: int | None = None
    value_decimal: str | None = None
    value_date: str | None = None
    value_boolean: bool | None = None
    confidence: float = 1.0
    review_status: str = "needs_review"
    observed_at: str | None = None


@dataclass(frozen=True)
class ObservationRecord(ObservationCreate):
    """Stored typed observation."""

    observation_id: int = 0
    observation_type_id: int = 0


@dataclass(frozen=True)
class ObservationEvidenceCreate:
    """Input data for creating observation evidence."""

    observation_id: int
    document_id: int
    extraction_run_id: int | None = None
    evidence_text: str | None = None
    page_number: int | None = None
    location_text: str | None = None


@dataclass(frozen=True)
class ObservationEvidenceRecord(ObservationEvidenceCreate):
    """Stored observation evidence."""

    observation_evidence_id: int = 0
