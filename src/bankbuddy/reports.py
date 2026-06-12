"""Reporting query helpers."""

from __future__ import annotations

from dataclasses import dataclass

from bankbuddy.database import connect_database, initialize_database
from bankbuddy.paths import AppPaths


@dataclass(frozen=True)
class SpendingReportRow:
    """A spending summary row prepared for CLI display."""

    category_name: str
    currency: str
    transaction_count: int
    spending_minor_units: int


def spending_report(
    paths: AppPaths,
    *,
    year: int,
    month: int | None = None,
) -> list[SpendingReportRow]:
    """Return outgoing spending grouped by currency and category."""

    initialize_database(paths)
    date_from = f"{year:04d}-{month or 1:02d}-01"
    date_to = f"{year:04d}-{month:02d}-31" if month is not None else f"{year:04d}-12-31"

    with connect_database(paths) as conn:
        rows = conn.execute(
            """
            select
                categories.category_name,
                transactions.currency,
                count(*) as transaction_count,
                sum(-transactions.amount_minor_units) as spending_minor_units
            from transactions
            join categories using (category_id)
            where transactions.transaction_date >= ?
              and transactions.transaction_date <= ?
              and transactions.amount_minor_units < 0
              and transactions.transfer_status != 'confirmed'
            group by transactions.currency, categories.category_name
            order by transactions.currency, spending_minor_units desc, categories.category_name
            """,
            (date_from, date_to),
        ).fetchall()

    return [
        SpendingReportRow(
            category_name=row["category_name"],
            currency=row["currency"],
            transaction_count=int(row["transaction_count"]),
            spending_minor_units=int(row["spending_minor_units"]),
        )
        for row in rows
    ]
