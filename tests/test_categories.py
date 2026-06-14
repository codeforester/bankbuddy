from bankbuddy import categories
from bankbuddy.paths import resolve_app_paths


def test_list_categories_returns_seeded_categories(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    rows = categories.list_categories(paths)

    assert rows[0].category_name == "Dining"
    assert rows[0].category_kind == "expense"
    assert rows[0].is_system is True
    assert "Uncategorized" in [row.category_name for row in rows]


def test_resolve_category_id_matches_names_case_insensitively(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    category_id = categories.resolve_category_id(paths, "groceries")

    rows = categories.list_categories(paths)
    groceries = next(row for row in rows if row.category_name == "Groceries")
    assert category_id == groceries.category_id


def test_resolve_category_id_rejects_unknown_category(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    try:
        categories.resolve_category_id(paths, "Made Up")
    except categories.CategoryError as exc:
        assert str(exc) == "Category not found: Made Up"
    else:
        raise AssertionError("Expected unknown category to fail")
