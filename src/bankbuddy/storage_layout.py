"""Storage layout migration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import sqlite3

from bankbuddy.paths import AppPaths
from bankbuddy.paths import DATABASE_NAME


@dataclass(frozen=True)
class StoragePathMove:
    """A planned path move relative to the BankBuddy home directory."""

    source: str
    target: str


@dataclass(frozen=True)
class StorageLayoutMigrationSummary:
    """Summary of a storage layout migration plan or run."""

    dry_run: bool
    already_canonical: bool
    changes_applied: bool
    database_move: StoragePathMove | None
    directory_moves: tuple[StoragePathMove, ...]
    processed_paths_to_update: int
    duplicate_paths_to_update: int


class StorageLayoutError(RuntimeError):
    """Raised when a storage layout migration cannot be safely completed."""


def migrate_storage_layout(
    paths: AppPaths,
    *,
    dry_run: bool,
) -> StorageLayoutMigrationSummary:
    """Migrate a legacy BankBuddy home to the canonical storage layout."""

    if paths.layout == "canonical":
        return StorageLayoutMigrationSummary(
            dry_run=dry_run,
            already_canonical=True,
            changes_applied=False,
            database_move=None,
            directory_moves=(),
            processed_paths_to_update=0,
            duplicate_paths_to_update=0,
        )

    database_move = _database_move(paths)
    directory_moves = _directory_moves(paths)
    processed_paths_to_update = _count_prefixed_paths(
        paths.database,
        table_name="import_files",
        column_name="processed_path",
        prefix="processed/",
    )
    duplicate_paths_to_update = _count_prefixed_paths(
        paths.database,
        table_name="import_attempts",
        column_name="duplicate_path",
        prefix="duplicates/",
    )

    if not dry_run:
        _assert_targets_available(paths, database_move, directory_moves)
        _apply_database_move(paths, database_move)
        _apply_directory_moves(paths, directory_moves)
        _update_database_paths(paths.root / "database" / DATABASE_NAME)

    return StorageLayoutMigrationSummary(
        dry_run=dry_run,
        already_canonical=False,
        changes_applied=not dry_run,
        database_move=database_move,
        directory_moves=directory_moves,
        processed_paths_to_update=processed_paths_to_update,
        duplicate_paths_to_update=duplicate_paths_to_update,
    )


def _database_move(paths: AppPaths) -> StoragePathMove | None:
    source = paths.root / DATABASE_NAME
    if not source.exists():
        return None
    return StoragePathMove(
        source=DATABASE_NAME,
        target=f"database/{DATABASE_NAME}",
    )


def _directory_moves(paths: AppPaths) -> tuple[StoragePathMove, ...]:
    moves: list[StoragePathMove] = []
    for directory_name in ("inbox", "processed", "duplicates", "exports"):
        source = paths.root / directory_name
        if source.exists():
            moves.append(
                StoragePathMove(
                    source=directory_name,
                    target=f"bank/{directory_name}",
                )
            )
    return tuple(moves)


def _assert_targets_available(
    paths: AppPaths,
    database_move: StoragePathMove | None,
    directory_moves: tuple[StoragePathMove, ...],
) -> None:
    moves = list(directory_moves)
    if database_move is not None:
        moves.append(database_move)

    for move in moves:
        target = paths.root / move.target
        if target.exists():
            raise StorageLayoutError(
                f"Cannot migrate storage layout because target already exists: "
                f"{move.target}"
            )


def _apply_database_move(
    paths: AppPaths,
    database_move: StoragePathMove | None,
) -> None:
    if database_move is None:
        return
    source = paths.root / database_move.source
    target = paths.root / database_move.target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))


def _apply_directory_moves(
    paths: AppPaths,
    directory_moves: tuple[StoragePathMove, ...],
) -> None:
    for move in directory_moves:
        source = paths.root / move.source
        target = paths.root / move.target
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))


def _count_prefixed_paths(
    database_path: Path,
    *,
    table_name: str,
    column_name: str,
    prefix: str,
) -> int:
    if not database_path.exists():
        return 0
    try:
        with sqlite3.connect(database_path) as conn:
            row = conn.execute(
                f"""
                select count(*)
                from {table_name}
                where {column_name} like ?
                """,
                (f"{prefix}%",),
            ).fetchone()
    except sqlite3.Error:
        return 0
    return int(row[0])


def _update_database_paths(database_path: Path) -> None:
    if not database_path.exists():
        return
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            """
            update import_files
            set processed_path = 'bank/' || processed_path
            where processed_path like 'processed/%'
            """
        )
        conn.execute(
            """
            update import_attempts
            set duplicate_path = 'bank/' || duplicate_path
            where duplicate_path like 'duplicates/%'
            """
        )
        conn.commit()
