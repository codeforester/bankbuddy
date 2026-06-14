"""Account statement reference persistence and matching."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3

from bankbuddy.accounts import masked_account_number
from bankbuddy.database import connect_database, initialize_database
from bankbuddy.paths import AppPaths


SOURCE_FORMAT_ANY = "*"
REF_TYPES = {
    "full_account_number",
    "last4",
    "masked_account",
    "product",
}
REF_TYPE_ALIASES = {
    "full-account-number": "full_account_number",
    "fullaccountnumber": "full_account_number",
    "full_account_number": "full_account_number",
    "last-4": "last4",
    "last_four": "last4",
    "last4": "last4",
    "masked-account": "masked_account",
    "maskedaccount": "masked_account",
    "masked_account": "masked_account",
    "product": "product",
}


class AccountStatementRefError(ValueError):
    """Raised when account statement refs cannot be managed or matched."""


class AccountStatementRefAlreadyExistsError(AccountStatementRefError):
    """Raised when the same statement ref already exists for an account."""


class AccountStatementRefNotFoundError(AccountStatementRefError):
    """Raised when a statement ref id is not configured."""


class AccountStatementRefAmbiguousError(AccountStatementRefError):
    """Raised when a statement ref maps to multiple configured accounts."""


@dataclass(frozen=True)
class StatementAccountRef:
    """An account identity found in statement content."""

    ref_type: str
    ref_value: str


@dataclass(frozen=True)
class AccountStatementRef:
    """A configured parser-visible account reference."""

    statement_ref_id: int
    account_id: int
    bank_name: str
    account_display: str | None
    account_type: str
    currency: str
    source_format: str
    ref_type: str
    ref_value: str
    normalized_ref_value: str


@dataclass(frozen=True)
class AccountRefMatch:
    """The account matched by statement content."""

    account_id: int
    ref_type: str
    normalized_ref_value: str


def add_account_statement_ref(
    paths: AppPaths,
    *,
    account_id: int,
    ref_type: str,
    ref_value: str,
    source_format: str | None = None,
) -> AccountStatementRef:
    """Add a parser-visible statement reference for an account."""

    initialize_database(paths)
    normalized_type = normalize_ref_type(ref_type)
    normalized_value = normalize_statement_ref_value(normalized_type, ref_value)
    normalized_source = normalize_source_format(source_format)
    with connect_database(paths) as conn:
        account = conn.execute(
            """
            select
                accounts.account_id,
                accounts.bank_id,
                accounts.currency,
                banks.bank_name
            from accounts
            join banks using (bank_id)
            where account_id = ?
            """,
            (account_id,),
        ).fetchone()
        if account is None:
            raise AccountStatementRefError(f"Account not found: {account_id}")
        ensure_ref_is_unambiguous(
            conn,
            account=account,
            source_format=normalized_source,
            ref_type=normalized_type,
            normalized_ref_value=normalized_value,
        )
        try:
            cursor = conn.execute(
                """
                insert into account_statement_refs (
                    account_id,
                    source_format,
                    ref_type,
                    ref_value,
                    normalized_ref_value
                ) values (?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    normalized_source,
                    normalized_type,
                    ref_value.strip(),
                    normalized_value,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AccountStatementRefAlreadyExistsError(
                "Account statement ref already exists for this account."
            ) from exc
        conn.commit()
        ref = get_account_statement_ref(conn, int(cursor.lastrowid))
        if ref is None:
            raise AccountStatementRefError("Account statement ref was not saved.")
        return ref


def ensure_ref_is_unambiguous(
    conn: sqlite3.Connection,
    *,
    account: sqlite3.Row,
    source_format: str,
    ref_type: str,
    normalized_ref_value: str,
) -> None:
    """Reject a ref that would make account matching ambiguous."""

    rows = conn.execute(
        """
        select distinct
            accounts.account_id
        from account_statement_refs
        join accounts using (account_id)
        where accounts.bank_id = ?
          and accounts.currency = ?
          and accounts.account_id != ?
          and account_statement_refs.ref_type = ?
          and account_statement_refs.normalized_ref_value = ?
          and (
              account_statement_refs.source_format = ?
              or account_statement_refs.source_format = ?
              or ? = ?
          )
        order by accounts.account_id
        """,
        (
            account["bank_id"],
            account["currency"],
            account["account_id"],
            ref_type,
            normalized_ref_value,
            source_format,
            SOURCE_FORMAT_ANY,
            source_format,
            SOURCE_FORMAT_ANY,
        ),
    ).fetchall()
    if not rows:
        return
    existing_ids = ", ".join(str(row["account_id"]) for row in rows)
    raise AccountStatementRefError(
        f"Account statement ref would be ambiguous for {account['bank_name']} "
        f"{account['currency']}; it already maps to account {existing_ids}."
    )


def list_account_statement_refs(
    paths: AppPaths,
    *,
    account_id: int | None = None,
) -> list[AccountStatementRef]:
    """Return configured statement refs."""

    initialize_database(paths)
    clauses: list[str] = []
    params: list[object] = []
    if account_id is not None:
        clauses.append("accounts.account_id = ?")
        params.append(account_id)
    where_sql = f"where {' and '.join(clauses)}" if clauses else ""
    with connect_database(paths) as conn:
        rows = conn.execute(
            account_statement_ref_select_sql()
            + where_sql
            + """
            order by
                banks.bank_name,
                accounts.account_id,
                account_statement_refs.source_format,
                account_statement_refs.ref_type,
                account_statement_refs.account_statement_ref_id
            """,
            params,
        ).fetchall()
    return [account_statement_ref_from_row(row) for row in rows]


def remove_account_statement_ref(
    paths: AppPaths,
    *,
    statement_ref_id: int,
) -> None:
    """Remove a configured statement ref."""

    initialize_database(paths)
    with connect_database(paths) as conn:
        cursor = conn.execute(
            """
            delete from account_statement_refs
            where account_statement_ref_id = ?
            """,
            (statement_ref_id,),
        )
        if cursor.rowcount == 0:
            raise AccountStatementRefNotFoundError(
                f"Account statement ref not found: {statement_ref_id}"
            )
        conn.commit()


def resolve_statement_account_ref(
    conn: sqlite3.Connection,
    *,
    bank_name: str,
    currency: str,
    source_format: str,
    statement_refs: tuple[StatementAccountRef, ...],
) -> AccountRefMatch | None:
    """Resolve statement refs to one configured account."""

    matches: dict[int, AccountRefMatch] = {}
    for statement_ref in statement_refs:
        normalized_type = normalize_ref_type(statement_ref.ref_type)
        normalized_value = normalize_statement_ref_value(
            normalized_type,
            statement_ref.ref_value,
        )
        for account_id in account_ids_for_configured_ref(
            conn,
            bank_name=bank_name,
            currency=currency,
            source_format=source_format,
            ref_type=normalized_type,
            normalized_ref_value=normalized_value,
        ):
            matches.setdefault(
                account_id,
                AccountRefMatch(
                    account_id=account_id,
                    ref_type=normalized_type,
                    normalized_ref_value=normalized_value,
                ),
            )
        if normalized_type == "full_account_number":
            for account_id in account_ids_for_full_account_number(
                conn,
                bank_name=bank_name,
                currency=currency,
                normalized_ref_value=normalized_value,
            ):
                matches.setdefault(
                    account_id,
                    AccountRefMatch(
                        account_id=account_id,
                        ref_type=normalized_type,
                        normalized_ref_value=normalized_value,
                    ),
                )

    if not matches:
        return None
    if len(matches) > 1:
        account_ids = ", ".join(str(account_id) for account_id in sorted(matches))
        raise AccountStatementRefAmbiguousError(
            f"Statement references map to multiple accounts: {account_ids}."
        )
    return next(iter(matches.values()))


def account_ids_for_configured_ref(
    conn: sqlite3.Connection,
    *,
    bank_name: str,
    currency: str,
    source_format: str,
    ref_type: str,
    normalized_ref_value: str,
) -> list[int]:
    """Return accounts with matching configured statement refs."""

    normalized_source = normalize_source_format(source_format)
    rows = conn.execute(
        """
        select distinct accounts.account_id
        from account_statement_refs
        join accounts using (account_id)
        join banks using (bank_id)
        where banks.bank_name = ?
          and accounts.currency = ?
          and account_statement_refs.ref_type = ?
          and account_statement_refs.normalized_ref_value = ?
          and account_statement_refs.source_format in (?, ?)
        order by accounts.account_id
        """,
        (
            bank_name,
            currency,
            ref_type,
            normalized_ref_value,
            normalized_source,
            SOURCE_FORMAT_ANY,
        ),
    ).fetchall()
    return [int(row["account_id"]) for row in rows]


def account_ids_for_full_account_number(
    conn: sqlite3.Connection,
    *,
    bank_name: str,
    currency: str,
    normalized_ref_value: str,
) -> list[int]:
    """Return accounts whose stored account number matches a full statement number."""

    rows = conn.execute(
        """
        select accounts.account_id, accounts.account_number
        from accounts
        join banks using (bank_id)
        where banks.bank_name = ?
          and accounts.currency = ?
        order by accounts.account_id
        """,
        (bank_name, currency),
    ).fetchall()
    return [
        int(row["account_id"])
        for row in rows
        if normalize_digits(row["account_number"]) == normalized_ref_value
    ]


def statement_refs_for_account_number(
    account_number: str | None,
) -> tuple[StatementAccountRef, ...]:
    """Return statement refs implied by a parser-visible account number."""

    normalized = normalize_digits(account_number or "")
    if not normalized:
        return ()
    return (
        StatementAccountRef(
            ref_type="full_account_number",
            ref_value=normalized,
        ),
    )


def get_account_statement_ref(
    conn: sqlite3.Connection,
    statement_ref_id: int,
) -> AccountStatementRef | None:
    """Return one statement ref from an open connection."""

    row = conn.execute(
        account_statement_ref_select_sql()
        + """
        where account_statement_refs.account_statement_ref_id = ?
        """,
        (statement_ref_id,),
    ).fetchone()
    if row is None:
        return None
    return account_statement_ref_from_row(row)


def account_statement_ref_select_sql() -> str:
    """Return the common statement-ref select clause."""

    return """
        select
            account_statement_refs.account_statement_ref_id,
            account_statement_refs.account_id,
            account_statement_refs.source_format,
            account_statement_refs.ref_type,
            account_statement_refs.ref_value,
            account_statement_refs.normalized_ref_value,
            banks.bank_name,
            accounts.display_name as account_display,
            accounts.account_type,
            accounts.currency
        from account_statement_refs
        join accounts using (account_id)
        join banks using (bank_id)
        """


def account_statement_ref_from_row(row: sqlite3.Row) -> AccountStatementRef:
    """Build an account statement ref dataclass from a SQLite row."""

    return AccountStatementRef(
        statement_ref_id=int(row["account_statement_ref_id"]),
        account_id=int(row["account_id"]),
        bank_name=row["bank_name"],
        account_display=row["account_display"],
        account_type=row["account_type"],
        currency=row["currency"],
        source_format=row["source_format"],
        ref_type=row["ref_type"],
        ref_value=row["ref_value"],
        normalized_ref_value=row["normalized_ref_value"],
    )


def normalize_ref_type(ref_type: str) -> str:
    """Return a canonical statement ref type."""

    key = ref_type.strip().lower()
    normalized = REF_TYPE_ALIASES.get(key)
    if normalized is None:
        supported = ", ".join(sorted(REF_TYPES))
        raise AccountStatementRefError(
            f"Unsupported account statement ref type {ref_type!r}. "
            f"Use one of: {supported}."
        )
    return normalized


def normalize_source_format(source_format: str | None) -> str:
    """Return a canonical source-format selector."""

    if source_format is None:
        return SOURCE_FORMAT_ANY
    stripped = source_format.strip().lower()
    if stripped in {"", "any", SOURCE_FORMAT_ANY}:
        return SOURCE_FORMAT_ANY
    return stripped


def display_source_format(source_format: str) -> str:
    """Return the user-facing source format selector."""

    return "any" if source_format == SOURCE_FORMAT_ANY else source_format


def normalize_statement_ref_value(ref_type: str, ref_value: str) -> str:
    """Return a canonical statement ref value for matching."""

    normalized_type = normalize_ref_type(ref_type)
    if normalized_type in {"full_account_number", "last4", "masked_account"}:
        normalized = normalize_digits(ref_value)
        if not normalized:
            raise AccountStatementRefError(
                "Numeric account statement refs must contain at least one digit."
            )
        if normalized_type == "last4" and len(normalized) != 4:
            raise AccountStatementRefError("last4 refs must contain exactly 4 digits.")
        if (
            normalized_type in {"full_account_number", "masked_account"}
            and len(normalized) < 4
        ):
            raise AccountStatementRefError(
                f"{normalized_type} refs must contain at least 4 digits."
            )
        if normalized_type == "masked_account" and len(normalized) > 4:
            return normalized[-4:]
        return normalized

    normalized = re.sub(r"[^a-z0-9]+", "-", ref_value.strip().lower()).strip("-")
    if not normalized:
        raise AccountStatementRefError("Product refs cannot be empty.")
    return normalized


def display_ref_value(ref: AccountStatementRef) -> str:
    """Return a safe display value for a statement ref."""

    if ref.ref_type == "full_account_number":
        return masked_account_number(ref.normalized_ref_value)
    if ref.ref_type == "masked_account":
        return masked_account_number(ref.normalized_ref_value)
    return ref.normalized_ref_value


def normalize_digits(value: str) -> str:
    """Return digits from an account-like identifier."""

    return "".join(character for character in value if character.isdigit())
