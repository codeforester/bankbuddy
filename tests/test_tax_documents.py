import pytest

from bankbuddy.database import connect_database
from bankbuddy.paths import resolve_app_paths
from bankbuddy.tax.documents import canonical_tax_document_filename
from bankbuddy.tax.documents import get_tax_document
from bankbuddy.tax.documents import import_tax_document
from bankbuddy.tax.documents import list_tax_documents
from bankbuddy.tax.documents import parse_tax_document_text
from bankbuddy.tax.documents import plan_tax_document_archive
from bankbuddy.tax.documents import plan_tax_document_import
from bankbuddy.tax.documents import TaxImportFailure


US_1099_INT_TEXT = """\
Form 1099-INT
Tax Year 2025
Payer: Bank of America
Account number ending in 1234
"""


def test_parse_tax_document_text_detects_us_1099_int_metadata() -> None:
    metadata = parse_tax_document_text(US_1099_INT_TEXT)

    assert metadata.jurisdiction == "US"
    assert metadata.document_type == "1099-INT"
    assert metadata.tax_year == 2025
    assert metadata.source_entity == "Bank of America"
    assert metadata.account_ref == "1234"
    assert metadata.person_label is None


def test_parse_tax_document_text_rejects_ambiguous_metadata() -> None:
    with pytest.raises(TaxImportFailure, match="missing a tax year"):
        parse_tax_document_text("Form 1099-INT\nPayer: Bank of America\n")


def test_plan_tax_document_archive_uses_canonical_tax_hierarchy(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    source_path = tmp_path / "download.pdf"
    source_path.write_bytes(b"tax document")
    metadata = parse_tax_document_text(US_1099_INT_TEXT)

    archive = plan_tax_document_archive(
        paths,
        source_path=source_path,
        metadata=metadata,
        file_hash="abcd1234",
    )

    assert canonical_tax_document_filename(metadata, suffix=".pdf") == (
        "2025_1099-int_bank-of-america_1234.pdf"
    )
    assert archive.canonical_file_name == "2025_1099-int_bank-of-america_1234.pdf"
    assert archive.processed_path == (
        "tax/processed/us/2025/1099-int/"
        "2025_1099-int_bank-of-america_1234.pdf"
    )
    assert not (paths.root / archive.processed_path).exists()


def test_plan_tax_document_import_is_read_only(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    source_path = tmp_path / "boa-1099.txt"
    source_path.write_text(US_1099_INT_TEXT, encoding="utf-8")

    plan = plan_tax_document_import(paths, source_path)

    assert plan.file_name == "boa-1099.txt"
    assert plan.document_type == "1099-INT"
    assert plan.jurisdiction == "US"
    assert plan.tax_year == 2025
    assert plan.source_entity == "Bank of America"
    assert plan.account_ref == "1234"
    assert plan.duplicate is False
    assert plan.existing_document_id is None
    assert plan.processed_path == (
        "tax/processed/us/2025/1099-int/"
        "2025_1099-int_bank-of-america_1234.txt"
    )
    assert not (paths.root / plan.processed_path).exists()
    assert not paths.database.exists()


def test_import_tax_document_archives_and_indexes_document(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    source_path = tmp_path / "boa-1099.txt"
    source_path.write_text(US_1099_INT_TEXT, encoding="utf-8")

    summary = import_tax_document(paths, source_path)

    assert summary.tax_document_id == 1
    assert summary.duplicate is False
    assert summary.document_type == "1099-INT"
    assert summary.jurisdiction == "US"
    assert summary.tax_year == 2025
    assert summary.source_entity == "Bank of America"
    assert summary.processed_path == (
        "tax/processed/us/2025/1099-int/"
        "2025_1099-int_bank-of-america_1234.txt"
    )
    assert (paths.root / summary.processed_path).read_text(encoding="utf-8") == (
        US_1099_INT_TEXT
    )

    rows = list_tax_documents(paths)
    assert len(rows) == 1
    assert rows[0].tax_document_id == 1
    assert rows[0].canonical_file_name == "2025_1099-int_bank-of-america_1234.txt"
    assert rows[0].processed_path == summary.processed_path


def test_import_tax_document_is_idempotent_by_file_hash(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    source_path = tmp_path / "boa-1099.txt"
    source_path.write_text(US_1099_INT_TEXT, encoding="utf-8")

    first = import_tax_document(paths, source_path)
    second = import_tax_document(paths, source_path)

    assert first.tax_document_id == second.tax_document_id
    assert second.duplicate is True
    with connect_database(paths) as conn:
        count = conn.execute("select count(*) from tax_documents").fetchone()[0]
    assert count == 1


def test_list_and_get_tax_documents_filter_metadata(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    first_path = tmp_path / "boa-1099.txt"
    first_path.write_text(US_1099_INT_TEXT, encoding="utf-8")
    second_path = tmp_path / "w2.txt"
    second_path.write_text(
        "Form W-2\nTax Year 2024\nEmployer: Example Employer\n",
        encoding="utf-8",
    )
    import_tax_document(paths, first_path)
    import_tax_document(paths, second_path)

    year_rows = list_tax_documents(paths, year=2025)
    type_rows = list_tax_documents(paths, document_type="w-2")
    document = get_tax_document(paths, 1)

    assert [row.tax_document_id for row in year_rows] == [1]
    assert [row.tax_document_id for row in type_rows] == [2]
    assert document.tax_document_id == 1
    assert document.document_type == "1099-INT"
    assert document.source_entity == "Bank of America"
