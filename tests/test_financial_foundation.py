from bankbuddy.database import connect_database, initialize_database
from bankbuddy.financial.dao import FinancialIntelligenceDAO
from bankbuddy.financial.records import (
    DocumentCreate,
    EntityAttributeCreate,
    EntityCreate,
    ObservationCreate,
    ObservationEvidenceCreate,
)
from bankbuddy.paths import resolve_app_paths


def test_financial_foundation_schema_is_additive_and_seeded(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)

    with connect_database(paths) as conn:
        table_names = {
            row["name"]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
        index_names = {
            row["name"]
            for row in conn.execute(
                "select name from sqlite_master where type = 'index'"
            ).fetchall()
        }
        dao = FinancialIntelligenceDAO(conn)

        entity_attribute_codes = {
            row.attribute_code for row in dao.list_entity_attribute_types()
        }
        relationship_type_codes = {
            row.relationship_type_code for row in dao.list_relationship_types()
        }
        observation_type_codes = {
            row.observation_type_code for row in dao.list_observation_types()
        }

    assert {"banks", "accounts", "transactions", "tax_documents"}.issubset(
        table_names
    )
    assert {
        "BB_DOCUMENT",
        "BB_IMPORT_ATTEMPT",
        "BB_PARSER",
        "BB_EXTRACTION_RUN",
        "BB_ENTITY",
        "BB_ENTITY_ATTRIBUTE_TYPE",
        "BB_ENTITY_ATTRIBUTE",
        "BB_RELATIONSHIP_TYPE",
        "BB_RELATIONSHIP",
        "BB_OBSERVATION_TYPE",
        "BB_OBSERVATION",
        "BB_OBSERVATION_EVIDENCE",
        "BB_PERSON",
        "BB_HOUSEHOLD",
        "BB_HOUSEHOLD_MEMBER",
        "BB_CURRENCY",
        "BB_JURISDICTION",
    }.issubset(table_names)
    assert {
        "idx_BB_DOCUMENT_file_hash",
        "idx_BB_PARSER_file_type",
        "idx_BB_ENTITY_type_status",
        "idx_BB_ENTITY_ATTRIBUTE_entity_type",
        "idx_BB_OBSERVATION_subject_type",
        "idx_BB_RELATIONSHIP_source_type",
    }.issubset(index_names)
    assert {
        "ACCOUNT_NUMBER",
        "ACCOUNT_LAST4",
        "ADDRESS_LINE_1",
        "ADDRESS_CITY",
        "ADDRESS_COUNTRY",
        "JURISDICTION",
    }.issubset(entity_attribute_codes)
    assert {"OWNS", "MEMBER_OF_HOUSEHOLD", "HELD_AT_INSTITUTION"}.issubset(
        relationship_type_codes
    )
    assert {
        "DOCUMENT_TYPE",
        "STATEMENT_PERIOD",
        "ACCOUNT_BALANCE",
        "TAX_YEAR",
    }.issubset(observation_type_codes)


def test_financial_dao_round_trips_records_without_inline_sql_callers(
    tmp_path,
) -> None:
    paths = resolve_app_paths(tmp_path)
    initialize_database(paths)

    with connect_database(paths) as conn:
        dao = FinancialIntelligenceDAO(conn)
        document = dao.create_document(
            DocumentCreate(
                file_hash="a" * 64,
                original_file_name="statement.pdf",
                canonical_file_name="bank_1234_2026-01-01_2026-01-31.pdf",
                document_type="bank_statement",
                jurisdiction_code="US",
                tax_year=2026,
            )
        )
        fetched_document = dao.find_document_by_hash("a" * 64)
        entity = dao.create_entity(
            EntityCreate(entity_type="account", display_name="Everyday Checking")
        )
        attribute = dao.add_entity_attribute(
            EntityAttributeCreate(
                entity_id=entity.entity_id,
                attribute_type_code="ACCOUNT_LAST4",
                value_text="1234",
                source_document_id=document.document_id,
            )
        )
        observation = dao.create_observation(
            ObservationCreate(
                observation_type_code="STATEMENT_PERIOD",
                document_id=document.document_id,
                subject_entity_id=entity.entity_id,
                value_text="2026-01-01/2026-01-31",
                confidence=1.0,
                review_status="accepted",
            )
        )
        evidence = dao.add_observation_evidence(
            ObservationEvidenceCreate(
                observation_id=observation.observation_id,
                document_id=document.document_id,
                evidence_text="Statement Period 01/01/26 to 01/31/26",
                page_number=1,
                location_text="page header",
            )
        )

    assert fetched_document is not None
    assert fetched_document.document_id == document.document_id
    assert fetched_document.file_hash == "a" * 64
    assert document.document_status == "active"
    assert entity.entity_type == "account"
    assert attribute.attribute_type_code == "ACCOUNT_LAST4"
    assert attribute.value_text == "1234"
    assert observation.observation_type_code == "STATEMENT_PERIOD"
    assert observation.review_status == "accepted"
    assert evidence.observation_id == observation.observation_id
