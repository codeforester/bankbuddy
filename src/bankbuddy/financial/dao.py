"""Data access objects for financial intelligence v2 tables."""

from __future__ import annotations

import sqlite3

from bankbuddy.financial.records import (
    DocumentCreate,
    DocumentRecord,
    EntityAttributeCreate,
    EntityAttributeRecord,
    EntityAttributeTypeRecord,
    EntityCreate,
    EntityRecord,
    ObservationCreate,
    ObservationRecord,
    ObservationEvidenceCreate,
    ObservationEvidenceRecord,
    ObservationTypeRecord,
    RelationshipTypeRecord,
)


class FinancialReferenceTypeNotFoundError(ValueError):
    """Raised when a requested v2 reference/type code is not seeded."""


class FinancialIntelligenceDAO:
    """Persistence boundary for v2 financial intelligence tables."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_entity_attribute_types(self) -> list[EntityAttributeTypeRecord]:
        """Return seeded entity attribute types ordered by code."""

        rows = self._conn.execute(
            """
            select
                entity_attribute_type_id,
                attribute_code,
                display_name,
                value_kind,
                sensitivity,
                is_system
            from BB_ENTITY_ATTRIBUTE_TYPE
            order by attribute_code
            """
        ).fetchall()
        return [
            EntityAttributeTypeRecord(
                entity_attribute_type_id=int(row["entity_attribute_type_id"]),
                attribute_code=str(row["attribute_code"]),
                display_name=str(row["display_name"]),
                value_kind=str(row["value_kind"]),
                sensitivity=str(row["sensitivity"]),
                is_system=bool(row["is_system"]),
            )
            for row in rows
        ]

    def list_relationship_types(self) -> list[RelationshipTypeRecord]:
        """Return seeded relationship types ordered by code."""

        rows = self._conn.execute(
            """
            select
                relationship_type_id,
                relationship_type_code,
                display_name,
                is_system
            from BB_RELATIONSHIP_TYPE
            order by relationship_type_code
            """
        ).fetchall()
        return [
            RelationshipTypeRecord(
                relationship_type_id=int(row["relationship_type_id"]),
                relationship_type_code=str(row["relationship_type_code"]),
                display_name=str(row["display_name"]),
                is_system=bool(row["is_system"]),
            )
            for row in rows
        ]

    def list_observation_types(self) -> list[ObservationTypeRecord]:
        """Return seeded observation types ordered by code."""

        rows = self._conn.execute(
            """
            select
                observation_type_id,
                observation_type_code,
                display_name,
                value_kind,
                is_system
            from BB_OBSERVATION_TYPE
            order by observation_type_code
            """
        ).fetchall()
        return [
            ObservationTypeRecord(
                observation_type_id=int(row["observation_type_id"]),
                observation_type_code=str(row["observation_type_code"]),
                display_name=str(row["display_name"]),
                value_kind=str(row["value_kind"]),
                is_system=bool(row["is_system"]),
            )
            for row in rows
        ]

    def create_document(self, record: DocumentCreate) -> DocumentRecord:
        """Create a v2 document row."""

        cursor = self._conn.execute(
            """
            insert into BB_DOCUMENT (
                file_hash,
                original_file_name,
                canonical_file_name,
                storage_path,
                source_uri,
                document_type,
                jurisdiction_code,
                tax_year,
                document_status
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.file_hash,
                record.original_file_name,
                record.canonical_file_name,
                record.storage_path,
                record.source_uri,
                record.document_type,
                record.jurisdiction_code,
                record.tax_year,
                record.document_status,
            ),
        )
        return DocumentRecord(document_id=int(cursor.lastrowid), **record.__dict__)

    def find_document_by_hash(self, file_hash: str) -> DocumentRecord | None:
        """Return a v2 document by file hash."""

        row = self._conn.execute(
            """
            select
                document_id,
                file_hash,
                original_file_name,
                canonical_file_name,
                storage_path,
                source_uri,
                document_type,
                jurisdiction_code,
                tax_year,
                document_status
            from BB_DOCUMENT
            where file_hash = ?
            """,
            (file_hash,),
        ).fetchone()
        if row is None:
            return None
        return _document_from_row(row)

    def create_entity(self, record: EntityCreate) -> EntityRecord:
        """Create a v2 entity row."""

        cursor = self._conn.execute(
            """
            insert into BB_ENTITY (
                entity_type,
                display_name,
                status
            ) values (?, ?, ?)
            """,
            (record.entity_type, record.display_name, record.status),
        )
        return EntityRecord(entity_id=int(cursor.lastrowid), **record.__dict__)

    def add_entity_attribute(
        self,
        record: EntityAttributeCreate,
    ) -> EntityAttributeRecord:
        """Create a typed attribute for a v2 entity."""

        attribute_type_id = self._type_id_for_code(
            table_name="BB_ENTITY_ATTRIBUTE_TYPE",
            id_column="entity_attribute_type_id",
            code_column="attribute_code",
            code=record.attribute_type_code,
        )
        cursor = self._conn.execute(
            """
            insert into BB_ENTITY_ATTRIBUTE (
                entity_id,
                entity_attribute_type_id,
                value_text,
                value_integer,
                value_decimal,
                value_date,
                value_boolean,
                source_document_id,
                valid_from,
                valid_to
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.entity_id,
                attribute_type_id,
                record.value_text,
                record.value_integer,
                record.value_decimal,
                record.value_date,
                _bool_to_int(record.value_boolean),
                record.source_document_id,
                record.valid_from,
                record.valid_to,
            ),
        )
        return EntityAttributeRecord(
            entity_attribute_id=int(cursor.lastrowid),
            entity_attribute_type_id=attribute_type_id,
            **record.__dict__,
        )

    def create_observation(self, record: ObservationCreate) -> ObservationRecord:
        """Create a typed observation."""

        observation_type_id = self._type_id_for_code(
            table_name="BB_OBSERVATION_TYPE",
            id_column="observation_type_id",
            code_column="observation_type_code",
            code=record.observation_type_code,
        )
        cursor = self._conn.execute(
            """
            insert into BB_OBSERVATION (
                observation_type_id,
                document_id,
                subject_entity_id,
                value_text,
                value_integer,
                value_decimal,
                value_date,
                value_boolean,
                confidence,
                review_status,
                observed_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_type_id,
                record.document_id,
                record.subject_entity_id,
                record.value_text,
                record.value_integer,
                record.value_decimal,
                record.value_date,
                _bool_to_int(record.value_boolean),
                record.confidence,
                record.review_status,
                record.observed_at,
            ),
        )
        return ObservationRecord(
            observation_id=int(cursor.lastrowid),
            observation_type_id=observation_type_id,
            **record.__dict__,
        )

    def add_observation_evidence(
        self,
        record: ObservationEvidenceCreate,
    ) -> ObservationEvidenceRecord:
        """Create evidence for an observation."""

        cursor = self._conn.execute(
            """
            insert into BB_OBSERVATION_EVIDENCE (
                observation_id,
                document_id,
                extraction_run_id,
                evidence_text,
                page_number,
                location_text
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                record.observation_id,
                record.document_id,
                record.extraction_run_id,
                record.evidence_text,
                record.page_number,
                record.location_text,
            ),
        )
        return ObservationEvidenceRecord(
            observation_evidence_id=int(cursor.lastrowid),
            **record.__dict__,
        )

    def _type_id_for_code(
        self,
        *,
        table_name: str,
        id_column: str,
        code_column: str,
        code: str,
    ) -> int:
        row = self._conn.execute(
            f"select {id_column} from {table_name} where {code_column} = ?",
            (code,),
        ).fetchone()
        if row is None:
            raise FinancialReferenceTypeNotFoundError(
                f"Unknown financial reference type: {code}"
            )
        return int(row[id_column])


def _document_from_row(row: sqlite3.Row) -> DocumentRecord:
    return DocumentRecord(
        document_id=int(row["document_id"]),
        file_hash=str(row["file_hash"]),
        original_file_name=str(row["original_file_name"]),
        canonical_file_name=row["canonical_file_name"],
        storage_path=row["storage_path"],
        source_uri=row["source_uri"],
        document_type=row["document_type"],
        jurisdiction_code=row["jurisdiction_code"],
        tax_year=row["tax_year"],
        document_status=str(row["document_status"]),
    )


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return int(value)
