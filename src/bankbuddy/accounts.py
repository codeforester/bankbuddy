"""Account persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from bankbuddy.currency import normalize_currency
from bankbuddy.database import connect_database, initialize_database
from bankbuddy.paths import AppPaths


class AccountAlreadyExistsError(ValueError):
    """Raised when the bank/account identity is already configured."""


class AccountNotFoundError(ValueError):
    """Raised when an account id is not configured."""


class AccountUpdateError(ValueError):
    """Raised when an account update request is invalid."""


class BankAlreadyExistsError(ValueError):
    """Raised when a bank name already exists."""


class BankNotFoundError(ValueError):
    """Raised when a bank id is not configured."""


class CountryCodeError(ValueError):
    """Raised when a country value cannot be normalized."""


COUNTRY_ALIASES = {
    "in": "IN",
    "india": "IN",
    "us": "US",
    "usa": "US",
    "unitedstates": "US",
    "unitedstatesofamerica": "US",
}


@dataclass(frozen=True)
class Bank:
    """A configured financial institution."""

    bank_id: int
    bank_name: str
    country: str
    default_currency: str


@dataclass(frozen=True)
class Account:
    """A configured financial account."""

    account_id: int
    bank_name: str
    country: str
    account_number: str
    account_type: str
    currency: str
    statement_account_ref: str | None
    display_name: str | None


@dataclass(frozen=True)
class AccountSummary:
    """A configured account with latest balance snapshot metadata."""

    account_id: int
    bank_name: str
    country: str
    account_number: str
    account_type: str
    currency: str
    statement_account_ref: str | None
    display_name: str | None
    latest_balance_minor_units: int | None
    latest_balance_currency: str | None
    latest_balance_as_of_date: str | None
    latest_balance_source_file_id: int | None
    latest_balance_source: str | None


def add_account(
    paths: AppPaths,
    *,
    bank_name: str,
    country: str,
    account_number: str,
    account_type: str,
    currency: str,
    statement_account_ref: str | None = None,
    display_name: str | None = None,
) -> Account:
    """Create a bank account, creating the bank row when needed."""

    normalized_country = normalize_country_code(country)
    normalized_currency = normalize_currency(currency)
    initialize_database(paths)
    with connect_database(paths) as conn:
        bank_id = ensure_bank(
            conn,
            bank_name=bank_name,
            country=normalized_country,
            default_currency=normalized_currency,
        )
        try:
            cursor = conn.execute(
                """
                insert into accounts (
                    bank_id,
                    account_number,
                    account_type,
                    currency,
                    statement_account_ref,
                    display_name
                ) values (?, ?, ?, ?, ?, ?)
                """,
                (
                    bank_id,
                    account_number,
                    account_type,
                    normalized_currency,
                    empty_to_none(statement_account_ref),
                    empty_to_none(display_name),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AccountAlreadyExistsError(
                f"Account already exists for {bank_name}: "
                f"{masked_account_number(account_number)}"
            ) from exc
        conn.commit()
        return Account(
            account_id=int(cursor.lastrowid),
            bank_name=bank_name,
            country=normalized_country,
            account_number=account_number,
            account_type=account_type,
            currency=normalized_currency,
            statement_account_ref=empty_to_none(statement_account_ref),
            display_name=empty_to_none(display_name),
        )


def ensure_bank(
    conn: sqlite3.Connection,
    *,
    bank_name: str,
    country: str,
    default_currency: str,
) -> int:
    """Return an existing bank id or create the bank."""

    normalized_country = normalize_country_code(country)
    row = conn.execute(
        "select bank_id, country from banks where bank_name = ?",
        (bank_name,),
    ).fetchone()
    if row is not None:
        existing_country = normalize_country_code(row["country"])
        if existing_country != normalized_country:
            raise CountryCodeError(
                f"Bank {bank_name} is already configured for country "
                f"{existing_country}; cannot add an account for "
                f"{normalized_country}."
            )
        if row["country"] != existing_country:
            conn.execute(
                "update banks set country = ?, updated_at = current_timestamp "
                "where bank_id = ?",
                (existing_country, row["bank_id"]),
            )
        return int(row["bank_id"])

    cursor = conn.execute(
        """
        insert into banks (bank_name, country, default_currency)
        values (?, ?, ?)
        """,
        (bank_name, normalized_country, default_currency),
    )
    return int(cursor.lastrowid)


def list_accounts(paths: AppPaths) -> list[Account]:
    """Return configured accounts ordered by bank and account id."""

    initialize_database(paths)
    with connect_database(paths) as conn:
        rows = conn.execute(
            account_select_query()
            + """
            order by banks.bank_name, accounts.account_id
            """
        ).fetchall()
    return [account_from_row(row) for row in rows]


def list_banks(paths: AppPaths) -> list[Bank]:
    """Return configured banks ordered by name."""

    initialize_database(paths)
    with connect_database(paths) as conn:
        rows = conn.execute(
            """
            select bank_id, bank_name, country, default_currency
            from banks
            order by bank_name, bank_id
            """
        ).fetchall()
    return [bank_from_row(row) for row in rows]


def rename_bank(
    paths: AppPaths,
    *,
    bank_id: int,
    bank_name: str,
) -> Bank:
    """Rename a configured bank."""

    normalized_bank_name = bank_name.strip()
    if not normalized_bank_name:
        raise ValueError("Bank name cannot be empty.")

    initialize_database(paths)
    with connect_database(paths) as conn:
        existing = conn.execute(
            "select bank_id from banks where bank_id = ?",
            (bank_id,),
        ).fetchone()
        if existing is None:
            raise BankNotFoundError(f"Bank not found: {bank_id}")

        try:
            conn.execute(
                """
                update banks
                set bank_name = ?,
                    updated_at = current_timestamp
                where bank_id = ?
                """,
                (normalized_bank_name, bank_id),
            )
        except sqlite3.IntegrityError as exc:
            raise BankAlreadyExistsError(
                f"Bank already exists: {normalized_bank_name}"
            ) from exc

        row = conn.execute(
            """
            select bank_id, bank_name, country, default_currency
            from banks
            where bank_id = ?
            """,
            (bank_id,),
        ).fetchone()
        conn.commit()
    return bank_from_row(row)


def update_account(
    paths: AppPaths,
    *,
    account_id: int,
    display_name: str | None = None,
) -> Account:
    """Update safe account metadata."""

    if display_name is None:
        raise AccountUpdateError("No account updates requested.")

    initialize_database(paths)
    with connect_database(paths) as conn:
        existing = conn.execute(
            "select account_id from accounts where account_id = ?",
            (account_id,),
        ).fetchone()
        if existing is None:
            raise AccountNotFoundError(f"Account not found: {account_id}")

        conn.execute(
            """
            update accounts
            set display_name = ?,
                updated_at = current_timestamp
            where account_id = ?
            """,
            (empty_to_none(display_name), account_id),
        )
        row = conn.execute(
            account_select_query()
            + """
            where accounts.account_id = ?
            """,
            (account_id,),
        ).fetchone()
        conn.commit()
    return account_from_row(row)


def list_account_summaries(paths: AppPaths) -> list[AccountSummary]:
    """Return configured accounts with latest balance metadata."""

    initialize_database(paths)
    with connect_database(paths) as conn:
        rows = conn.execute(
            account_summary_query()
            + """
            order by banks.bank_name, accounts.account_id
            """
        ).fetchall()
    return [account_summary_from_row(row) for row in rows]


def get_account_summary(
    paths: AppPaths,
    *,
    account_id: int,
) -> AccountSummary | None:
    """Return one configured account with latest balance metadata."""

    initialize_database(paths)
    with connect_database(paths) as conn:
        row = conn.execute(
            account_summary_query()
            + """
            where accounts.account_id = ?
            """,
            (account_id,),
        ).fetchone()
    if row is None:
        return None
    return account_summary_from_row(row)


def account_summary_query() -> str:
    """Return the common account summary select clause."""

    return """
        select
            accounts.account_id,
            banks.bank_name,
            banks.country,
            accounts.account_number,
            accounts.account_type,
            accounts.currency,
            accounts.statement_account_ref,
            accounts.display_name,
            accounts.latest_balance_minor_units,
            accounts.latest_balance_currency,
            accounts.latest_balance_as_of_date,
            accounts.latest_balance_source_file_id,
            coalesce(
                import_files.canonical_file_name,
                import_files.file_name
            ) as latest_balance_source
        from accounts
        join banks using (bank_id)
        left join import_files
          on import_files.file_id = accounts.latest_balance_source_file_id
        """


def account_summary_from_row(row: sqlite3.Row) -> AccountSummary:
    """Build an account summary dataclass from a SQLite row."""

    return AccountSummary(
        account_id=int(row["account_id"]),
        bank_name=row["bank_name"],
        country=row["country"],
        account_number=row["account_number"],
        account_type=row["account_type"],
        currency=row["currency"],
        statement_account_ref=row["statement_account_ref"],
        display_name=row["display_name"],
        latest_balance_minor_units=row["latest_balance_minor_units"],
        latest_balance_currency=row["latest_balance_currency"],
        latest_balance_as_of_date=row["latest_balance_as_of_date"],
        latest_balance_source_file_id=row["latest_balance_source_file_id"],
        latest_balance_source=row["latest_balance_source"],
    )


def account_select_query() -> str:
    """Return the common account select clause."""

    return """
        select
            accounts.account_id,
            banks.bank_name,
            banks.country,
            accounts.account_number,
            accounts.account_type,
            accounts.currency,
            accounts.statement_account_ref,
            accounts.display_name
        from accounts
        join banks using (bank_id)
        """


def account_from_row(row: sqlite3.Row) -> Account:
    """Build an account dataclass from a SQLite row."""

    return Account(
        account_id=int(row["account_id"]),
        bank_name=row["bank_name"],
        country=row["country"],
        account_number=row["account_number"],
        account_type=row["account_type"],
        currency=row["currency"],
        statement_account_ref=row["statement_account_ref"],
        display_name=row["display_name"],
    )


def bank_from_row(row: sqlite3.Row) -> Bank:
    """Build a bank dataclass from a SQLite row."""

    return Bank(
        bank_id=int(row["bank_id"]),
        bank_name=row["bank_name"],
        country=row["country"],
        default_currency=row["default_currency"],
    )


def masked_account_number(account_number: str) -> str:
    """Return a display-safe account suffix."""

    suffix = account_number[-4:] if len(account_number) >= 4 else account_number
    return f"...{suffix}"


def empty_to_none(value: str | None) -> str | None:
    """Normalize empty CLI option values to NULL."""

    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def normalize_country_code(value: str) -> str:
    """Return a supported ISO 3166-1 alpha-2 country code."""

    normalized_key = "".join(
        character.lower()
        for character in value.strip()
        if character.isalnum()
    )
    country_code = COUNTRY_ALIASES.get(normalized_key)
    if country_code is None:
        raise CountryCodeError(
            f"Unsupported country {value!r}. Use a supported ISO 3166-1 "
            "alpha-2 country code such as US or IN."
        )
    return country_code
