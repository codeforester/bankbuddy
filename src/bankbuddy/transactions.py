"""Transaction query helpers."""

from __future__ import annotations

from dataclasses import dataclass

from bankbuddy.accounts import masked_account_number
from bankbuddy.database import connect_database, initialize_database
from bankbuddy.paths import AppPaths


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


def list_transactions(
    paths: AppPaths,
    *,
    account_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[TransactionRow]:
    """Return imported transactions ordered by date and id."""

    initialize_database(paths)
    conditions: list[str] = []
    parameters: list[object] = []
    if account_id is not None:
        conditions.append("transactions.account_id = ?")
        parameters.append(account_id)
    if date_from is not None:
        conditions.append("transactions.transaction_date >= ?")
        parameters.append(date_from)
    if date_to is not None:
        conditions.append("transactions.transaction_date <= ?")
        parameters.append(date_to)

    where_clause = f"where {' and '.join(conditions)}" if conditions else ""
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
            {where_clause}
            order by transactions.transaction_date, transactions.transaction_id
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


def format_minor_units(minor_units: int) -> str:
    """Format minor units as a signed decimal amount without a currency code."""

    sign = "-" if minor_units < 0 else ""
    absolute_minor_units = abs(minor_units)
    major_units = absolute_minor_units // 100
    fractional_units = absolute_minor_units % 100
    return f"{sign}{major_units}.{fractional_units:02d}"
