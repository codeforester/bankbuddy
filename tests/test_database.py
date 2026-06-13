import sqlite3

import pytest

from bankbuddy.database import Migration, apply_migrations, connect_database, initialize_database
from bankbuddy.paths import resolve_app_paths


def test_initialize_database_creates_directories_and_schema_table(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)

    assert paths.inbox.is_dir()
    assert paths.processed.is_dir()
    assert paths.exports.is_dir()
    assert paths.database.is_file()

    with sqlite3.connect(paths.database) as conn:
        row = conn.execute(
            "select name from sqlite_master where type = 'table' and name = 'schema_migrations'"
        ).fetchone()

    assert row == ("schema_migrations",)


def test_initialize_database_applies_core_schema_and_seed_categories(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)

    with sqlite3.connect(paths.database) as conn:
        table_names = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
        migration_versions = [
            row[0]
            for row in conn.execute(
                "select version from schema_migrations order by version"
            ).fetchall()
        ]
        categories = {
            row[0]: row[1]
            for row in conn.execute(
                "select category_name, category_kind from categories order by category_name"
            ).fetchall()
        }

    assert {
        "schema_migrations",
        "banks",
        "accounts",
        "categories",
        "transactions",
        "import_files",
        "import_attempts",
        "category_rules",
        "budgets",
    }.issubset(table_names)
    assert migration_versions == [
        "0001_core_schema",
        "0002_import_file_metadata",
        "0003_import_attempt_account",
        "0004_duplicate_import_attempts",
    ]
    assert categories == {
        "Dining": "expense",
        "Dividends": "income",
        "Education": "expense",
        "Entertainment": "expense",
        "Groceries": "expense",
        "Healthcare": "expense",
        "Insurance": "expense",
        "Interest": "income",
        "Rent / Mortgage": "expense",
        "Salary": "income",
        "Shopping": "expense",
        "Transfer": "special",
        "Travel": "expense",
        "Uncategorized": "special",
        "Utilities": "expense",
    }


def test_initialize_database_is_idempotent(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)
    initialize_database(paths)

    with sqlite3.connect(paths.database) as conn:
        migration_count = conn.execute(
            "select count(*) from schema_migrations"
        ).fetchone()[0]
        category_count = conn.execute("select count(*) from categories").fetchone()[0]

    assert migration_count == 4
    assert category_count == 15


def test_import_attempts_schema_tracks_account_id(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)

    with sqlite3.connect(paths.database) as conn:
        columns = {
            row[1]: row[2]
            for row in conn.execute("pragma table_info(import_attempts)").fetchall()
        }

    assert columns["account_id"] == "INTEGER"


def test_import_attempts_schema_allows_duplicate_status_and_path(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)

    with connect_database(paths) as conn:
        columns = {
            row[1]: row[2]
            for row in conn.execute("pragma table_info(import_attempts)").fetchall()
        }
        conn.execute(
            "insert into import_files (file_name, file_hash) values (?, ?)",
            ("statement.csv", "file-hash"),
        )
        file_id = conn.execute("select file_id from import_files").fetchone()["file_id"]
        conn.execute(
            """
            insert into import_attempts (
                file_id,
                import_status,
                finished_at,
                duplicate_path
            ) values (?, ?, current_timestamp, ?)
            """,
            (
                file_id,
                "duplicate",
                "duplicates/bank-of-america/2026/06/statement.csv",
            ),
        )
        attempt = conn.execute(
            "select import_status, duplicate_path from import_attempts"
        ).fetchone()

    assert columns["duplicate_path"] == "TEXT"
    assert attempt["import_status"] == "duplicate"
    assert (
        attempt["duplicate_path"]
        == "duplicates/bank-of-america/2026/06/statement.csv"
    )


def test_import_files_schema_tracks_canonical_archive_metadata(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)

    with sqlite3.connect(paths.database) as conn:
        columns = {
            row[1]
            for row in conn.execute("pragma table_info(import_files)").fetchall()
        }

    assert {
        "original_file_name",
        "canonical_file_name",
        "source_path",
        "processed_path",
        "statement_start_date",
        "statement_end_date",
        "account_ref",
        "source_format",
    }.issubset(columns)


def test_apply_migrations_rolls_back_failed_migration(tmp_path, monkeypatch) -> None:
    paths = resolve_app_paths(tmp_path)
    broken_migration = Migration(
        version="9999_broken",
        name="9999_broken.sql",
        sql="""
        create table partial_migration (
            partial_id integer primary key
        );
        insert into missing_table (value) values ('boom');
        """,
    )
    monkeypatch.setattr(
        "bankbuddy.database.iter_migrations",
        lambda: [broken_migration],
    )

    with connect_database(paths) as conn:
        with pytest.raises(sqlite3.OperationalError):
            apply_migrations(conn)

        table_row = conn.execute(
            "select name from sqlite_master where type = 'table' and name = ?",
            ("partial_migration",),
        ).fetchone()
        migration_row = conn.execute(
            "select version from schema_migrations where version = ?",
            ("9999_broken",),
        ).fetchone()

    assert table_row is None
    assert migration_row is None


def test_core_schema_enforces_identity_and_currency_constraints(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)
    initialize_database(paths)

    with connect_database(paths) as conn:
        conn.execute(
            "insert into banks (bank_name, country, default_currency) values (?, ?, ?)",
            ("Bank of America", "US", "USD"),
        )
        bank_id = conn.execute("select bank_id from banks").fetchone()["bank_id"]
        conn.execute(
            """
            insert into accounts (
                bank_id,
                account_number,
                account_type,
                currency
            ) values (?, ?, ?, ?)
            """,
            (bank_id, "123456789", "checking", "USD"),
        )
        account_id = conn.execute("select account_id from accounts").fetchone()["account_id"]
        conn.execute(
            "insert into banks (bank_name, country, default_currency) values (?, ?, ?)",
            ("HDFC Bank", "India", "INR"),
        )
        inr_bank_id = conn.execute(
            "select bank_id from banks where bank_name = ?",
            ("HDFC Bank",),
        ).fetchone()["bank_id"]
        conn.execute(
            """
            insert into accounts (
                bank_id,
                account_number,
                account_type,
                currency
            ) values (?, ?, ?, ?)
            """,
            (inr_bank_id, "000111222333", "savings", "INR"),
        )
        category_id = conn.execute(
            "select category_id from categories where category_name = 'Uncategorized'"
        ).fetchone()["category_id"]
        conn.execute(
            """
            insert into import_files (file_name, file_hash, bank_id)
            values (?, ?, ?)
            """,
            ("boa.csv", "file-hash", bank_id),
        )
        file_id = conn.execute("select file_id from import_files").fetchone()["file_id"]

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                insert into accounts (
                    bank_id,
                    account_number,
                    account_type,
                    currency
                ) values (?, ?, ?, ?)
                """,
                (bank_id, "123456789", "checking", "USD"),
            )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                insert into accounts (
                    bank_id,
                    account_number,
                    account_type,
                    currency
                ) values (?, ?, ?, ?)
                """,
                (bank_id, "987654321", "checking", "EUR"),
            )

        conn.execute(
            """
            insert into transactions (
                account_id,
                category_id,
                file_id,
                transaction_date,
                amount_minor_units,
                currency,
                description,
                normalized_description,
                transaction_hash,
                transfer_status
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                category_id,
                file_id,
                "2026-06-11",
                -1234,
                "USD",
                "Coffee",
                "coffee",
                "tx-hash",
                "none",
            ),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                insert into transactions (
                    account_id,
                    category_id,
                    file_id,
                    transaction_date,
                    amount_minor_units,
                    currency,
                    description,
                    normalized_description,
                    transaction_hash,
                    transfer_status
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    category_id,
                    file_id,
                    "2026-06-11",
                    -1234,
                    "USD",
                    "Coffee",
                    "coffee",
                    "tx-hash",
                    "none",
                ),
            )


def test_project_connections_enforce_foreign_keys(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)
    initialize_database(paths)

    with connect_database(paths) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                insert into accounts (
                    bank_id,
                    account_number,
                    account_type,
                    currency
                ) values (?, ?, ?, ?)
                """,
                (999, "123456789", "checking", "USD"),
            )
