from bankbuddy.database import connect_database
from bankbuddy.database import initialize_database
from bankbuddy.paths import ensure_app_dirs
from bankbuddy.paths import resolve_app_paths
from bankbuddy.storage_layout import migrate_storage_layout


def test_migrate_storage_layout_dry_run_reports_legacy_moves_without_changes(
    tmp_path,
) -> None:
    legacy_paths = resolve_app_paths(tmp_path / "home", layout="legacy")
    initialize_database(legacy_paths)
    _seed_legacy_archive(legacy_paths)

    summary = migrate_storage_layout(legacy_paths, dry_run=True)

    assert summary.dry_run is True
    assert summary.already_canonical is False
    assert summary.changes_applied is False
    assert summary.database_move is not None
    assert summary.database_move.source == "bankbuddy.sqlite3"
    assert summary.database_move.target == "database/bankbuddy.sqlite3"
    assert {move.source for move in summary.directory_moves} == {
        "inbox",
        "processed",
        "duplicates",
        "exports",
    }
    assert summary.processed_paths_to_update == 1
    assert summary.duplicate_paths_to_update == 1
    assert (legacy_paths.root / "bankbuddy.sqlite3").is_file()
    assert (
        legacy_paths.root / "processed/bank-of-america/2026/06/statement.pdf"
    ).is_file()

    with connect_database(legacy_paths) as conn:
        file_row = conn.execute("select processed_path from import_files").fetchone()
        attempt_row = conn.execute(
            "select duplicate_path from import_attempts"
        ).fetchone()

    assert file_row["processed_path"] == (
        "processed/bank-of-america/2026/06/statement.pdf"
    )
    assert attempt_row["duplicate_path"] == (
        "duplicates/bank-of-america/2026/06/statement.pdf"
    )


def test_migrate_storage_layout_moves_files_and_updates_database_paths(
    tmp_path,
) -> None:
    legacy_paths = resolve_app_paths(tmp_path / "home", layout="legacy")
    initialize_database(legacy_paths)
    _seed_legacy_archive(legacy_paths)

    summary = migrate_storage_layout(legacy_paths, dry_run=False)

    assert summary.dry_run is False
    assert summary.already_canonical is False
    assert summary.changes_applied is True
    assert (legacy_paths.root / "database/bankbuddy.sqlite3").is_file()
    assert (legacy_paths.root / "bank/inbox/pending.pdf").is_file()
    assert (
        legacy_paths.root / "bank/processed/bank-of-america/2026/06/statement.pdf"
    ).is_file()
    assert (
        legacy_paths.root / "bank/duplicates/bank-of-america/2026/06/statement.pdf"
    ).is_file()
    assert (legacy_paths.root / "bank/exports/snapshot.sqlite3").is_file()
    assert not (legacy_paths.root / "bankbuddy.sqlite3").exists()
    assert not (legacy_paths.root / "processed").exists()
    assert resolve_app_paths(legacy_paths.root).layout == "canonical"

    canonical_paths = resolve_app_paths(legacy_paths.root)
    with connect_database(canonical_paths) as conn:
        file_row = conn.execute("select processed_path from import_files").fetchone()
        attempt_row = conn.execute(
            "select duplicate_path from import_attempts"
        ).fetchone()

    assert file_row["processed_path"] == (
        "bank/processed/bank-of-america/2026/06/statement.pdf"
    )
    assert attempt_row["duplicate_path"] == (
        "bank/duplicates/bank-of-america/2026/06/statement.pdf"
    )


def test_migrate_storage_layout_is_noop_for_canonical_home(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path / "home")
    initialize_database(paths)

    summary = migrate_storage_layout(paths, dry_run=True)

    assert summary.dry_run is True
    assert summary.already_canonical is True
    assert summary.changes_applied is False
    assert summary.database_move is None
    assert summary.directory_moves == ()
    assert summary.processed_paths_to_update == 0
    assert summary.duplicate_paths_to_update == 0


def _seed_legacy_archive(paths) -> None:
    ensure_app_dirs(paths)
    processed_path = "processed/bank-of-america/2026/06/statement.pdf"
    duplicate_path = "duplicates/bank-of-america/2026/06/statement.pdf"
    inbox_path = paths.root / "inbox/pending.pdf"
    export_path = paths.root / "exports/snapshot.sqlite3"

    (paths.root / processed_path).parent.mkdir(parents=True, exist_ok=True)
    (paths.root / processed_path).write_bytes(b"processed statement")
    (paths.root / duplicate_path).parent.mkdir(parents=True, exist_ok=True)
    (paths.root / duplicate_path).write_bytes(b"duplicate statement")
    inbox_path.write_bytes(b"pending statement")
    export_path.write_bytes(b"export contents")

    with connect_database(paths) as conn:
        conn.execute(
            """
            insert into import_files (
                file_name,
                file_hash,
                processed_path
            )
            values (?, ?, ?)
            """,
            ("statement.pdf", "hash-1", processed_path),
        )
        file_id = conn.execute("select file_id from import_files").fetchone()[
            "file_id"
        ]
        conn.execute(
            """
            insert into import_attempts (
                file_id,
                import_status,
                duplicate_path
            )
            values (?, ?, ?)
            """,
            (file_id, "duplicate", duplicate_path),
        )
        conn.commit()
