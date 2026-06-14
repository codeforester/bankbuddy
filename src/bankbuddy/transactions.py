"""Transaction query helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from typing import Iterable
from typing import Literal

from bankbuddy.accounts import masked_account_number
from bankbuddy.currency import normalize_currency
from bankbuddy.database import connect_database, initialize_database
from bankbuddy.paths import AppPaths


SortDirection = Literal["asc", "desc"]


@dataclass(frozen=True)
class TransactionRow:
    """A transaction row prepared for CLI display."""

    transaction_id: int
    account_id: int
    transaction_date: str
    account_display: str
    amount_minor_units: int
    currency: str
    description: str


@dataclass(frozen=True)
class TransactionSort:
    """A validated transaction sort term."""

    field: str
    direction: SortDirection


@dataclass(frozen=True)
class TransactionSummary:
    """Aggregates for transaction rows in one currency."""

    currency: str
    transaction_count: int
    debit_minor_units: int
    credit_minor_units: int
    net_minor_units: int


class TransactionSortError(ValueError):
    """Raised when a transaction sort expression cannot be parsed."""


class TransactionFilterError(ValueError):
    """Raised when a transaction filter cannot be resolved safely."""


def list_transactions(
    paths: AppPaths,
    *,
    account_id: int | None = None,
    bank_name: str | None = None,
    currency: str | None = None,
    account_number: str | None = None,
    account_last4: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    direction: Literal["debit", "credit"] | None = None,
    sort: str | None = None,
    default_order: SortDirection = "asc",
) -> list[TransactionRow]:
    """Return imported transactions ordered by a validated sort expression."""

    initialize_database(paths)
    conditions: list[str] = []
    parameters: list[object] = []
    if account_id is not None:
        conditions.append("transactions.account_id = ?")
        parameters.append(account_id)
    if bank_name is not None:
        normalized_bank_name = bank_name.strip()
        if not normalized_bank_name:
            raise TransactionFilterError("Bank name must not be empty.")
        conditions.append("lower(banks.bank_name) = lower(?)")
        parameters.append(normalized_bank_name)
    if currency is not None:
        conditions.append("transactions.currency = ?")
        parameters.append(normalize_currency(currency))
    if account_number is not None:
        add_account_id_filter(
            conditions,
            parameters,
            account_ids_for_number(paths, account_number),
        )
    if account_last4 is not None:
        add_account_id_filter(
            conditions,
            parameters,
            [resolve_account_last4(paths, account_last4)],
        )
    if date_from is not None:
        conditions.append("transactions.transaction_date >= ?")
        parameters.append(date_from)
    if date_to is not None:
        conditions.append("transactions.transaction_date <= ?")
        parameters.append(date_to)
    if direction == "debit":
        conditions.append("transactions.amount_minor_units < 0")
    elif direction == "credit":
        conditions.append("transactions.amount_minor_units > 0")

    where_clause = f"where {' and '.join(conditions)}" if conditions else ""
    order_clause = build_order_clause(
        parse_sort_expression(sort, default_order=default_order)
    )
    with connect_database(paths) as conn:
        rows = conn.execute(
            f"""
            select
                transactions.transaction_id,
                transactions.account_id,
                transactions.transaction_date,
                transactions.amount_minor_units,
                transactions.currency,
                transactions.description,
                accounts.account_number,
                accounts.display_name
            from transactions
            join accounts using (account_id)
            join banks using (bank_id)
            {where_clause}
            {order_clause}
            """,
            parameters,
        ).fetchall()

    return [
        TransactionRow(
            transaction_id=int(row["transaction_id"]),
            account_id=int(row["account_id"]),
            transaction_date=row["transaction_date"],
            account_display=row["display_name"]
            or masked_account_number(row["account_number"]),
            amount_minor_units=int(row["amount_minor_units"]),
            currency=row["currency"],
            description=row["description"],
        )
        for row in rows
    ]


def account_ids_for_number(paths: AppPaths, account_number: str) -> list[int]:
    """Return account ids whose stored number matches after digit cleanup."""

    normalized_account_number = normalize_account_digits(account_number)
    if not normalized_account_number:
        return []

    with connect_database(paths) as conn:
        rows = conn.execute(
            """
            select account_id, account_number
            from accounts
            order by account_id
            """
        ).fetchall()

    return [
        int(row["account_id"])
        for row in rows
        if normalize_account_digits(row["account_number"])
        == normalized_account_number
    ]


def resolve_account_last4(paths: AppPaths, account_last4: str) -> int:
    """Resolve an account suffix to one configured account id."""

    suffix = normalize_account_digits(account_last4)
    if len(suffix) != 4:
        raise TransactionFilterError(
            "Account last four digits must contain exactly four digits."
        )

    with connect_database(paths) as conn:
        rows = conn.execute(
            """
            select account_id, account_number
            from accounts
            order by account_id
            """
        ).fetchall()

    matches = [
        int(row["account_id"])
        for row in rows
        if normalize_account_digits(row["account_number"]).endswith(suffix)
    ]
    if not matches:
        raise TransactionFilterError(
            f"No account matches last four digits: {suffix}."
        )
    if len(matches) > 1:
        raise TransactionFilterError(
            "Account last four digits are ambiguous: "
            f"{suffix}. Use --account-id or --account-number."
        )
    return matches[0]


def add_account_id_filter(
    conditions: list[str],
    parameters: list[object],
    account_ids: list[int],
) -> None:
    """Append a transaction account-id condition for resolved accounts."""

    if not account_ids:
        conditions.append("1 = 0")
        return

    placeholders = ", ".join("?" for _account_id in account_ids)
    conditions.append(f"transactions.account_id in ({placeholders})")
    parameters.extend(account_ids)


def normalize_account_digits(value: str) -> str:
    """Return only the digits from a user-entered account number."""

    return "".join(char for char in value if char.isdigit())


def parse_sort_expression(
    sort: str | None,
    *,
    default_order: SortDirection = "asc",
) -> list[TransactionSort]:
    """Parse a public transaction sort expression into validated terms."""

    normalized_default_order = normalize_sort_direction(default_order)
    if sort is None or sort.strip() == "":
        return [
            TransactionSort("date", "asc"),
            TransactionSort("id", "asc"),
        ]

    sort_terms: list[TransactionSort] = []
    seen_fields: set[str] = set()
    for raw_term in sort.split(","):
        term = raw_term.strip()
        if not term:
            raise TransactionSortError("Sort fields must not be empty.")

        pieces = [piece.strip().lower() for piece in term.split(":")]
        if len(pieces) > 2:
            raise TransactionSortError(f"Invalid sort field: {term}.")

        field = pieces[0]
        if field not in SORT_FIELD_SQL:
            raise TransactionSortError(f"Unsupported sort field: {field}.")

        term_direction = (
            normalize_sort_direction(pieces[1])
            if len(pieces) == 2
            else normalized_default_order
        )
        if field not in seen_fields:
            sort_terms.append(TransactionSort(field, term_direction))
            seen_fields.add(field)

    if "id" not in seen_fields:
        sort_terms.append(TransactionSort("id", "asc"))

    return sort_terms


def normalize_sort_direction(direction: str) -> SortDirection:
    """Return a normalized sort direction or raise a helpful error."""

    normalized = direction.strip().lower()
    if normalized not in {"asc", "desc"}:
        raise TransactionSortError(f"Unsupported sort direction: {direction}.")
    return cast(SortDirection, normalized)


def build_order_clause(sort_terms: list[TransactionSort]) -> str:
    """Build an ORDER BY clause from validated sort terms."""

    order_terms = [
        f"{SORT_FIELD_SQL[term.field]} {term.direction}"
        for term in sort_terms
    ]
    return f"order by {', '.join(order_terms)}"


SORT_FIELD_SQL = {
    "id": "transactions.transaction_id",
    "date": "transactions.transaction_date",
    "amount": "transactions.amount_minor_units",
    "account": "coalesce(accounts.display_name, accounts.account_number)",
    "currency": "transactions.currency",
    "description": "transactions.description",
}


def summarize_transactions(
    rows: Iterable[TransactionRow],
) -> list[TransactionSummary]:
    """Return per-currency totals for a transaction row set."""

    totals: dict[str, dict[str, int]] = {}
    for row in rows:
        summary = totals.setdefault(
            row.currency,
            {
                "transaction_count": 0,
                "debit_minor_units": 0,
                "credit_minor_units": 0,
                "net_minor_units": 0,
            },
        )
        summary["transaction_count"] += 1
        summary["net_minor_units"] += row.amount_minor_units
        if row.amount_minor_units < 0:
            summary["debit_minor_units"] += row.amount_minor_units
        elif row.amount_minor_units > 0:
            summary["credit_minor_units"] += row.amount_minor_units

    return [
        TransactionSummary(
            currency=currency,
            transaction_count=summary["transaction_count"],
            debit_minor_units=summary["debit_minor_units"],
            credit_minor_units=summary["credit_minor_units"],
            net_minor_units=summary["net_minor_units"],
        )
        for currency, summary in sorted(totals.items())
    ]


def format_minor_units(minor_units: int) -> str:
    """Format minor units as a signed decimal amount without a currency code."""

    sign = "-" if minor_units < 0 else ""
    absolute_minor_units = abs(minor_units)
    major_units = absolute_minor_units // 100
    fractional_units = absolute_minor_units % 100
    return f"{sign}{major_units}.{fractional_units:02d}"
