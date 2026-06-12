from bankbuddy.import_files import archive_statement_file
from bankbuddy.import_files import canonical_statement_filename
from bankbuddy.import_files import import_archive_relative_path
from bankbuddy.paths import ensure_app_dirs
from bankbuddy.paths import resolve_app_paths


def test_canonical_statement_filename_slugifies_bank_and_uses_period() -> None:
    filename = canonical_statement_filename(
        bank_name="Bank of America",
        account_ref="1145",
        statement_start_date="2026-04-23",
        statement_end_date="2026-05-19",
        suffix=".pdf",
    )

    assert filename == "bank-of-america_1145_2026-04-23_2026-05-19.pdf"


def test_import_archive_relative_path_groups_by_bank_year_and_month() -> None:
    relative_path = import_archive_relative_path(
        bank_name="Bank of America",
        statement_end_date="2026-05-19",
        canonical_file_name="bank-of-america_1145_2026-04-23_2026-05-19.pdf",
    )

    assert (
        relative_path.as_posix()
        == "processed/bank-of-america/2026/05/"
        "bank-of-america_1145_2026-04-23_2026-05-19.pdf"
    )


def test_archive_statement_file_copies_source_and_preserves_original(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    ensure_app_dirs(paths)
    source_path = tmp_path / "eStmt_2026-05-19.pdf"
    source_path.write_bytes(b"statement contents")

    metadata = archive_statement_file(
        paths,
        source_path=source_path,
        bank_name="Bank of America",
        account_ref="1145",
        statement_start_date="2026-04-23",
        statement_end_date="2026-05-19",
        source_format="boa_pdf",
        file_hash="abcd1234",
    )

    archived_path = paths.root / metadata.processed_path
    assert source_path.is_file()
    assert archived_path.is_file()
    assert archived_path.read_bytes() == b"statement contents"
    assert metadata.original_file_name == "eStmt_2026-05-19.pdf"
    assert metadata.canonical_file_name == (
        "bank-of-america_1145_2026-04-23_2026-05-19.pdf"
    )
    assert metadata.source_path == str(source_path.resolve())
    assert (
        metadata.processed_path
        == "processed/bank-of-america/2026/05/"
        "bank-of-america_1145_2026-04-23_2026-05-19.pdf"
    )
    assert metadata.statement_start_date == "2026-04-23"
    assert metadata.statement_end_date == "2026-05-19"
    assert metadata.account_ref == "1145"
    assert metadata.source_format == "boa_pdf"


def test_archive_statement_file_adds_hash_suffix_for_content_collision(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    ensure_app_dirs(paths)
    first_source = tmp_path / "first.pdf"
    second_source = tmp_path / "second.pdf"
    first_source.write_bytes(b"first contents")
    second_source.write_bytes(b"second contents")

    archive_statement_file(
        paths,
        source_path=first_source,
        bank_name="Bank of America",
        account_ref="1145",
        statement_start_date="2026-04-23",
        statement_end_date="2026-05-19",
        source_format="boa_pdf",
        file_hash="1111222233334444",
    )
    metadata = archive_statement_file(
        paths,
        source_path=second_source,
        bank_name="Bank of America",
        account_ref="1145",
        statement_start_date="2026-04-23",
        statement_end_date="2026-05-19",
        source_format="boa_pdf",
        file_hash="aaaabbbbccccdddd",
    )

    assert metadata.canonical_file_name == (
        "bank-of-america_1145_2026-04-23_2026-05-19-aaaabbbb.pdf"
    )
    assert (paths.root / metadata.processed_path).read_bytes() == b"second contents"
