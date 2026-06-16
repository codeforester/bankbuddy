import sqlite3

import pytest

from bankbuddy.database import (
    Migration,
    SCHEMA_MIGRATIONS_SQL,
    apply_migrations,
    connect_database,
    initialize_database,
    iter_migrations,
)
from bankbuddy.paths import resolve_app_paths


EXPECTED_MIGRATION_VERSIONS = [
    "0001_core_schema",
    "0002_import_file_metadata",
    "0003_import_attempt_account",
    "0004_duplicate_import_attempts",
    "0005_account_balances_and_value_dates",
    "0006_normalize_bank_country_codes",
    "0007_add_rental_income_category",
    "0008_account_statement_refs",
    "0009_tax_documents",
    "0010_financial_intelligence_foundation",
    "0011_financial_document_storage",
]


def test_initialize_database_creates_directories_and_schema_table(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)

    assert paths.inbox.is_dir()
    assert paths.processed.is_dir()
    assert paths.exports.is_dir()
    assert paths.financial_canonical.is_dir()
    assert paths.financial_views.is_dir()
    assert paths.financial_inbox.is_dir()
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
        "account_statement_refs",
        "tax_documents",
        "BB_STORAGE_ROOT",
        "BB_DOCUMENT_OBJECT",
        "BB_DOCUMENT_VIEW",
    }.issubset(table_names)
    assert migration_versions == EXPECTED_MIGRATION_VERSIONS
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
        "Rental Income": "income",
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

    assert migration_count == len(EXPECTED_MIGRATION_VERSIONS)
    assert category_count == 16


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


def test_schema_tracks_value_date_and_latest_account_balance(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)

    with sqlite3.connect(paths.database) as conn:
        transaction_columns = {
            row[1]: row[2]
            for row in conn.execute("pragma table_info(transactions)").fetchall()
        }
        account_columns = {
            row[1]: row[2]
            for row in conn.execute("pragma table_info(accounts)").fetchall()
        }
        migration_versions = [
            row[0]
            for row in conn.execute(
                "select version from schema_migrations order by version"
            ).fetchall()
        ]

    assert transaction_columns["value_date"] == "TEXT"
    assert account_columns["latest_balance_minor_units"] == "INTEGER"
    assert account_columns["latest_balance_currency"] == "TEXT"
    assert account_columns["latest_balance_as_of_date"] == "TEXT"
    assert account_columns["latest_balance_source_file_id"] == "INTEGER"
    assert migration_versions == EXPECTED_MIGRATION_VERSIONS


def test_schema_tracks_account_statement_refs(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)

    with sqlite3.connect(paths.database) as conn:
        columns = {
            row[1]: row[2]
            for row in conn.execute(
                "pragma table_info(account_statement_refs)"
            ).fetchall()
        }

    assert columns["account_statement_ref_id"] == "INTEGER"
    assert columns["account_id"] == "INTEGER"
    assert columns["source_format"] == "TEXT"
    assert columns["ref_type"] == "TEXT"
    assert columns["ref_value"] == "TEXT"
    assert columns["normalized_ref_value"] == "TEXT"


def test_tax_documents_schema_tracks_imported_document_metadata(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    initialize_database(paths)

    with connect_database(paths) as conn:
        columns = {
            row[1]: row[2]
            for row in conn.execute("pragma table_info(tax_documents)").fetchall()
        }
        migration_versions = [
            row["version"]
            for row in conn.execute(
                "select version from schema_migrations order by version"
            ).fetchall()
        ]
        conn.execute(
            """
            insert into tax_documents (
                file_hash,
                original_file_name,
                canonical_file_name,
                source_path,
                processed_path,
                document_type,
                jurisdiction,
                tax_year,
                source_entity,
                person_label,
                account_ref
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "hash-1099-int",
                "download.pdf",
                "2025_1099-int_bank-of-america_1234.pdf",
                "/tmp/download.pdf",
                "tax/processed/us/2025/1099-int/"
                "2025_1099-int_bank-of-america_1234.pdf",
                "1099-INT",
                "US",
                2025,
                "Bank of America",
                "ramesh",
                "1234",
            ),
        )
        row = conn.execute(
            """
            select
                document_type,
                jurisdiction,
                tax_year,
                source_entity,
                person_label,
                account_ref
            from tax_documents
            """
        ).fetchone()

    assert {
        "tax_document_id": "INTEGER",
        "file_hash": "TEXT",
        "original_file_name": "TEXT",
        "canonical_file_name": "TEXT",
        "source_path": "TEXT",
        "processed_path": "TEXT",
        "document_type": "TEXT",
        "jurisdiction": "TEXT",
        "tax_year": "INTEGER",
        "source_entity": "TEXT",
        "person_label": "TEXT",
        "account_ref": "TEXT",
        "imported_at": "TEXT",
    }.items() <= columns.items()
    assert "0009_tax_documents" in migration_versions
    assert migration_versions[-1] == "0011_financial_document_storage"
    assert dict(row) == {
        "document_type": "1099-INT",
        "jurisdiction": "US",
        "tax_year": 2025,
        "source_entity": "Bank of America",
        "person_label": "ramesh",
        "account_ref": "1234",
    }


def test_rental_income_category_migration_backfills_existing_databases(
    tmp_path,
) -> None:
    paths = resolve_app_paths(tmp_path)

    with connect_database(paths) as conn:
        conn.execute(SCHEMA_MIGRATIONS_SQL)
        for migration in iter_migrations():
            if migration.version == "0007_add_rental_income_category":
                continue
            migration_sql = migration.sql.replace(
                "    ('Rental Income', 'income', 1),\n",
                "",
            )
            conn.executescript(migration_sql)
            conn.execute(
                "insert into schema_migrations (version) values (?)",
                (migration.version,),
            )
        conn.commit()

        existing_row = conn.execute(
            "select category_id from categories where category_name = ?",
            ("Rental Income",),
        ).fetchone()

        apply_migrations(conn)

        migrated_row = conn.execute(
            """
            select category_kind, is_system
            from categories
            where category_name = ?
            """,
            ("Rental Income",),
        ).fetchone()

    assert existing_row is None
    assert migrated_row["category_kind"] == "income"
    assert migrated_row["is_system"] == 1


def test_country_code_migration_normalizes_legacy_bank_values(tmp_path) -> None:
    paths = resolve_app_paths(tmp_path)

    with connect_database(paths) as conn:
        conn.execute(SCHEMA_MIGRATIONS_SQL)
        for migration in iter_migrations():
            if migration.version == "0006_normalize_bank_country_codes":
                continue
            conn.executescript(migration.sql)
            conn.execute(
                "insert into schema_migrations (version) values (?)",
                (migration.version,),
            )
        conn.execute(
            "insert into banks (bank_name, country, default_currency) values (?, ?, ?)",
            ("Legacy US Bank", "USA", "USD"),
        )
        conn.execute(
            "insert into banks (bank_name, country, default_currency) values (?, ?, ?)",
            ("Legacy India Bank", "India", "INR"),
        )
        conn.commit()

        apply_migrations(conn)

        countries = {
            row["bank_name"]: row["country"]
            for row in conn.execute(
                "select bank_name, country from banks order by bank_name"
            ).fetchall()
        }

    assert countries == {
        "Legacy India Bank": "IN",
        "Legacy US Bank": "US",
    }


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
