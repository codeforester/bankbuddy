import stat

import pytest

from bankbuddy.database import connect_database
from bankbuddy.database import initialize_database
from bankbuddy.bb.dao import FinancialIntelligenceDAO
from bankbuddy.bb.records import DocumentCreate
from bankbuddy.paths import resolve_app_paths


def test_bb_storage_schema_seeds_roots(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")

    initialize_database(paths)

    with connect_database(paths) as conn:
        rows = conn.execute(
            """
            select storage_root_code, root_kind, base_path_key, relative_root
            from BB_STORAGE_ROOT
            order by storage_root_code
            """
        ).fetchall()

    assert [row["storage_root_code"] for row in rows] == [
        "FINANCIAL_CANONICAL",
        "FINANCIAL_DUPLICATES",
        "FINANCIAL_EXPORTS",
        "FINANCIAL_FAILED",
        "FINANCIAL_INBOX",
        "FINANCIAL_REVIEW",
        "FINANCIAL_VIEWS",
    ]
    assert {
        row["storage_root_code"]: (
            row["root_kind"],
            row["base_path_key"],
            row["relative_root"],
        )
        for row in rows
    } == {
        "FINANCIAL_CANONICAL": ("canonical", "app_root", "financial/canonical"),
        "FINANCIAL_DUPLICATES": ("duplicates", "app_root", "financial/duplicates"),
        "FINANCIAL_EXPORTS": ("exports", "app_root", "financial/exports"),
        "FINANCIAL_FAILED": ("failed", "app_root", "financial/failed"),
        "FINANCIAL_INBOX": ("inbox", "app_root", "financial/inbox"),
        "FINANCIAL_REVIEW": ("review", "app_root", "financial/review"),
        "FINANCIAL_VIEWS": ("view", "app_root", "financial/views"),
    }


def test_bb_storage_paths_are_separate_from_bank_and_tax_dirs(tmp_path) -> None:
    (
        _,
        _,
        _,
        _,
        ensure_financial_storage_dirs,
        _,
        _,
    ) = _storage_api()
    paths = resolve_app_paths(tmp_path / "home")

    ensure_financial_storage_dirs(paths)

    assert paths.financial_canonical == paths.root / "financial" / "canonical"
    assert paths.financial_views == paths.root / "financial" / "views"
    assert paths.financial_inbox == paths.root / "financial" / "inbox"
    assert paths.financial_failed == paths.root / "financial" / "failed"
    assert paths.financial_duplicates == paths.root / "financial" / "duplicates"
    assert paths.financial_review == paths.root / "financial" / "review"
    assert paths.financial_exports == paths.root / "financial" / "exports"
    assert paths.inbox == paths.root / "bank" / "inbox"
    assert paths.tax_inbox == paths.root / "tax" / "inbox"
    assert paths.financial_canonical.is_dir()
    assert paths.financial_views.is_dir()


def test_storage_dao_records_objects_and_views_without_absolute_paths(tmp_path) -> None:
    (
        DocumentObjectCreate,
        DocumentViewCreate,
        FinancialStorageDAO,
        _,
        _,
        object_key_for_hash,
        resolve_storage_path,
    ) = _storage_api()
    paths = resolve_app_paths(tmp_path / "home")
    file_hash = "0123456789abcdef" * 4

    initialize_database(paths)

    with connect_database(paths) as conn:
        document = FinancialIntelligenceDAO(conn).create_document(
            DocumentCreate(
                file_hash=file_hash,
                original_file_name="statement.pdf",
                document_type="bank_statement",
            )
        )
        storage = FinancialStorageDAO(conn)
        canonical_root = storage.get_storage_root("FINANCIAL_CANONICAL")
        views_root = storage.get_storage_root("FINANCIAL_VIEWS")
        object_record = storage.create_document_object(
            DocumentObjectCreate(
                document_id=document.document_id,
                storage_root_code="FINANCIAL_CANONICAL",
                object_key=object_key_for_hash(file_hash, ".pdf"),
                object_role="canonical",
                content_hash=file_hash,
                byte_size=1234,
                media_type="application/pdf",
                original_file_name="statement.pdf",
            )
        )
        view_record = storage.create_document_view(
            DocumentViewCreate(
                document_id=document.document_id,
                document_object_id=object_record.document_object_id,
                storage_root_code="FINANCIAL_VIEWS",
                view_name="bank/by-account",
                view_key=(
                    "bank/bank-of-america/2026/05/"
                    "bank-of-america_1145_2026-04-22_2026-05-19.pdf"
                ),
                expected_hash=file_hash,
                byte_size=1234,
            )
        )

    assert object_record.storage_root_id == canonical_root.storage_root_id
    assert object_record.object_key == f"sha256/01/23/{file_hash}.pdf"
    assert view_record.storage_root_id == views_root.storage_root_id
    assert view_record.materialization_kind == "copy"
    assert resolve_storage_path(paths, canonical_root, object_record.object_key) == (
        paths.financial_canonical / "sha256" / "01" / "23" / f"{file_hash}.pdf"
    )
    assert resolve_storage_path(paths, views_root, view_record.view_key) == (
        paths.financial_views
        / "bank"
        / "bank-of-america"
        / "2026"
        / "05"
        / "bank-of-america_1145_2026-04-22_2026-05-19.pdf"
    )
    assert str(paths.root) not in object_record.object_key
    assert str(paths.root) not in view_record.view_key


def test_v2_document_tables_do_not_keep_filesystem_paths(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")

    initialize_database(paths)

    with connect_database(paths) as conn:
        document_columns = {
            row["name"]
            for row in conn.execute("pragma table_info(BB_DOCUMENT)").fetchall()
        }
        import_attempt_columns = {
            row["name"]
            for row in conn.execute("pragma table_info(BB_IMPORT_ATTEMPT)").fetchall()
        }
        document = FinancialIntelligenceDAO(conn).create_document(
            DocumentCreate(
                file_hash="fedcba9876543210" * 4,
                original_file_name="statement.pdf",
                source_uri="external://manual-upload/statement.pdf",
            )
        )

    assert "storage_path" not in document_columns
    assert "source_path" not in import_attempt_columns
    assert "document_object_id" in import_attempt_columns
    assert not hasattr(document, "storage_path")
    assert document.source_uri == "external://manual-upload/statement.pdf"


def test_storage_dao_normalizes_keys_before_writing(tmp_path) -> None:
    (
        DocumentObjectCreate,
        _,
        FinancialStorageDAO,
        _,
        _,
        _,
        _,
    ) = _storage_api()
    paths = resolve_app_paths(tmp_path / "home")

    initialize_database(paths)

    with connect_database(paths) as conn:
        document = FinancialIntelligenceDAO(conn).create_document(
            DocumentCreate(
                file_hash="1234567890abcdef" * 4,
                original_file_name="statement.pdf",
            )
        )
        storage = FinancialStorageDAO(conn)
        object_record = storage.create_document_object(
            DocumentObjectCreate(
                document_id=document.document_id,
                storage_root_code="FINANCIAL_CANONICAL",
                object_key=" sha256/12/34/object.pdf ",
                object_role="canonical",
                content_hash="1234567890abcdef" * 4,
            )
        )
        row = conn.execute(
            """
            select object_key
            from BB_DOCUMENT_OBJECT
            where document_object_id = ?
            """,
            (object_record.document_object_id,),
        ).fetchone()

    assert object_record.object_key == "sha256/12/34/object.pdf"
    assert row["object_key"] == "sha256/12/34/object.pdf"


def test_storage_keys_reject_absolute_and_parent_traversal_paths(tmp_path) -> None:
    (
        DocumentObjectCreate,
        _,
        FinancialStorageDAO,
        FinancialStoragePathError,
        _,
        _,
        _,
    ) = _storage_api()
    from bankbuddy.bb.storage import validate_storage_key

    paths = resolve_app_paths(tmp_path / "home")

    initialize_database(paths)

    with connect_database(paths) as conn:
        document = FinancialIntelligenceDAO(conn).create_document(
            DocumentCreate(
                file_hash="abcdef" * 10 + "abcd",
                original_file_name="statement.pdf",
            )
        )
        storage = FinancialStorageDAO(conn)

        with pytest.raises(FinancialStoragePathError):
            storage.create_document_object(
                DocumentObjectCreate(
                    document_id=document.document_id,
                    storage_root_code="FINANCIAL_CANONICAL",
                    object_key="/absolute/path.pdf",
                    object_role="canonical",
                    content_hash="abcdef" * 10 + "abcd",
                )
            )

        with pytest.raises(FinancialStoragePathError):
            validate_storage_key("nested/../escape.pdf")

        with pytest.raises(FinancialStoragePathError):
            validate_storage_key("../escape.pdf")


def test_protect_managed_path_sets_read_only_modes(tmp_path) -> None:
    from bankbuddy.bb.storage import protect_managed_path

    managed_file = tmp_path / "financial" / "canonical" / "object.pdf"
    managed_file.parent.mkdir(parents=True)
    managed_file.write_bytes(b"%PDF-1.4 placeholder")
    managed_dir = tmp_path / "financial" / "views" / "bank"
    managed_dir.mkdir(parents=True)

    try:
        protect_managed_path(managed_file)
        protect_managed_path(managed_dir)

        assert stat.S_IMODE(managed_file.stat().st_mode) == 0o444
        assert stat.S_IMODE(managed_dir.stat().st_mode) == 0o555
    finally:
        managed_file.chmod(0o644)
        managed_dir.chmod(0o755)


def _storage_api():
    try:
        from bankbuddy.bb.records import DocumentObjectCreate
        from bankbuddy.bb.records import DocumentViewCreate
        from bankbuddy.bb.storage import FinancialStorageDAO
        from bankbuddy.bb.storage import FinancialStoragePathError
        from bankbuddy.bb.storage import ensure_financial_storage_dirs
        from bankbuddy.bb.storage import object_key_for_hash
        from bankbuddy.bb.storage import resolve_storage_path
    except ImportError as exc:
        pytest.fail(f"Financial storage API is not available: {exc}")

    return (
        DocumentObjectCreate,
        DocumentViewCreate,
        FinancialStorageDAO,
        FinancialStoragePathError,
        ensure_financial_storage_dirs,
        object_key_for_hash,
        resolve_storage_path,
    )
