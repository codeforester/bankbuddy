from hashlib import sha256

from click.testing import CliRunner

from bankbuddy.bb.cli import main
from bankbuddy.database import connect_database
from bankbuddy.paths import resolve_app_paths


def test_bb_documents_import_dry_run_reports_plan_without_writes(tmp_path) -> None:
    home = tmp_path / "home"
    source = tmp_path / "statement.pdf"
    source_bytes = b"%PDF-1.4 placeholder"
    source.write_bytes(source_bytes)
    file_hash = sha256(source_bytes).hexdigest()

    result = CliRunner().invoke(
        main,
        ["documents", "import", "--dry-run", "--file", str(source)],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Dry run: yes" in result.output
    assert "File: statement.pdf" in result.output
    assert f"SHA-256: {file_hash}" in result.output
    assert "Media type: application/pdf" in result.output
    assert (
        f"Canonical object: financial/canonical/sha256/{file_hash[:2]}/"
        f"{file_hash[2:4]}/{file_hash}.pdf"
    ) in result.output
    assert "Database changed: no" in result.output
    assert "Files changed: none" in result.output
    assert not (home / "database" / "bankbuddy.sqlite3").exists()
    assert not (home / "financial" / "canonical").exists()


def test_bb_documents_import_records_document_and_canonical_object(
    tmp_path,
) -> None:
    home = tmp_path / "home"
    source = tmp_path / "statement.pdf"
    source_bytes = b"%PDF-1.4 placeholder"
    source.write_bytes(source_bytes)
    file_hash = sha256(source_bytes).hexdigest()

    result = CliRunner().invoke(
        main,
        ["documents", "import", "--file", str(source)],
        env={"BANKBUDDY_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Dry run: no" in result.output
    assert "Document ID: 1" in result.output
    assert "Document object ID: 1" in result.output
    assert "Duplicate: no" in result.output
    canonical_path = (
        home / "financial" / "canonical" / "sha256" / file_hash[:2] / file_hash[2:4]
        / f"{file_hash}.pdf"
    )
    assert canonical_path.read_bytes() == source_bytes
    with connect_database(resolve_app_paths(home)) as conn:
        document_count = conn.execute("select count(*) from BB_DOCUMENT").fetchone()[0]
        object_count = conn.execute(
            "select count(*) from BB_DOCUMENT_OBJECT"
        ).fetchone()[0]
        document = conn.execute(
            """
            select file_hash, original_file_name
            from BB_DOCUMENT
            where document_id = 1
            """
        ).fetchone()
        document_object = conn.execute(
            """
            select object_key, object_role, content_hash, byte_size, media_type
            from BB_DOCUMENT_OBJECT
            where document_object_id = 1
            """
        ).fetchone()

    assert document_count == 1
    assert object_count == 1
    assert document["file_hash"] == file_hash
    assert document["original_file_name"] == "statement.pdf"
    assert document_object["object_key"] == (
        f"sha256/{file_hash[:2]}/{file_hash[2:4]}/{file_hash}.pdf"
    )
    assert document_object["object_role"] == "canonical"
    assert document_object["content_hash"] == file_hash
    assert document_object["byte_size"] == len(source_bytes)
    assert document_object["media_type"] == "application/pdf"


def test_bb_documents_import_is_idempotent_for_existing_hash(tmp_path) -> None:
    home = tmp_path / "home"
    source = tmp_path / "statement.pdf"
    source.write_bytes(b"%PDF-1.4 placeholder")

    runner = CliRunner()
    env = {"BANKBUDDY_HOME": str(home)}
    first = runner.invoke(main, ["documents", "import", "--file", str(source)], env=env)
    second = runner.invoke(main, ["documents", "import", "--file", str(source)], env=env)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Document ID: 1" in second.output
    assert "Document object ID: 1" in second.output
    assert "Duplicate: yes" in second.output
    with connect_database(resolve_app_paths(home)) as conn:
        document_count = conn.execute("select count(*) from BB_DOCUMENT").fetchone()[0]
        object_count = conn.execute(
            "select count(*) from BB_DOCUMENT_OBJECT"
        ).fetchone()[0]

    assert document_count == 1
    assert object_count == 1
