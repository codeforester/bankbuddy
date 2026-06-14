"""Account persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from bankbuddy.currency import normalize_currency
from bankbuddy.database import connect_database, initialize_database
from bankbuddy.paths import AppPaths


class AccountAlreadyExistsError(ValueError):
    """Raised when the bank/account identity is already configured."""


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
            """
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
            order by banks.bank_name, accounts.account_id
            """
        ).fetchall()
    return [
        Account(
            account_id=int(row["account_id"]),
            bank_name=row["bank_name"],
            country=row["country"],
            account_number=row["account_number"],
            account_type=row["account_type"],
            currency=row["currency"],
            statement_account_ref=row["statement_account_ref"],
            display_name=row["display_name"],
        )
        for row in rows
    ]


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
