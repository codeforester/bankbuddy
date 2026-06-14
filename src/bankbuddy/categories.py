"""Category query helpers."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from bankbuddy.database import connect_database, initialize_database
from bankbuddy.paths import AppPaths


UNCATEGORIZED_CATEGORY = "Uncategorized"


class CategoryError(ValueError):
    """Raised when a category cannot be resolved."""


@dataclass(frozen=True)
class Category:
    """A transaction category prepared for display or matching."""

    category_id: int
    category_name: str
    category_kind: str
    is_system: bool


def list_categories(paths: AppPaths) -> list[Category]:
    """Return categories ordered by name."""

    initialize_database(paths)
    with connect_database(paths) as conn:
        rows = conn.execute(
            """
            select
                category_id,
                category_name,
                category_kind,
                is_system
            from categories
            order by category_name
            """
        ).fetchall()
    return [category_from_row(row) for row in rows]


def resolve_category_id(paths: AppPaths, category_name: str) -> int:
    """Resolve a category name to its id."""

    initialize_database(paths)
    with connect_database(paths) as conn:
        category = find_category_by_name(conn, category_name)
    if category is None:
        raise CategoryError(f"Category not found: {category_name}")
    return category.category_id


def find_category_by_name(
    conn: sqlite3.Connection,
    category_name: str,
) -> Category | None:
    """Return a category by case-insensitive name."""

    normalized_name = category_name.strip()
    if not normalized_name:
        raise CategoryError("Category name must not be empty.")

    row = conn.execute(
        """
        select
            category_id,
            category_name,
            category_kind,
            is_system
        from categories
        where lower(category_name) = lower(?)
        """,
        (normalized_name,),
    ).fetchone()
    if row is None:
        return None
    return category_from_row(row)


def category_from_row(row: sqlite3.Row) -> Category:
    """Build a category dataclass from a SQLite row."""

    return Category(
        category_id=int(row["category_id"]),
        category_name=row["category_name"],
        category_kind=row["category_kind"],
        is_system=bool(row["is_system"]),
    )
