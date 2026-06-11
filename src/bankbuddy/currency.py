"""Currency parsing and formatting helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


SUPPORTED_CURRENCIES = frozenset({"USD", "INR"})
MINOR_UNITS_PER_MAJOR = Decimal("100")


@dataclass(frozen=True)
class CurrencyAmount:
    """A currency amount stored as integer minor units."""

    currency: str
    minor_units: int


def normalize_currency(currency: str) -> str:
    """Normalize and validate an ISO currency code."""

    normalized = currency.upper()
    if normalized not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency: {normalized}")
    return normalized


def parse_amount(value: str, currency: str) -> CurrencyAmount:
    """Parse a display amount into integer minor units."""

    normalized_currency = normalize_currency(currency)
    cleaned = (
        value.strip()
        .replace(",", "")
        .replace("$", "")
        .replace("₹", "")
        .replace("INR", "")
        .replace("USD", "")
        .strip()
    )

    try:
        major_units = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid amount: {value}") from exc

    minor_units = int(
        (major_units * MINOR_UNITS_PER_MAJOR).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )
    return CurrencyAmount(normalized_currency, minor_units)


def format_amount(amount: CurrencyAmount) -> str:
    """Format integer minor units with an ISO currency code."""

    currency = normalize_currency(amount.currency)
    sign = "-" if amount.minor_units < 0 else ""
    absolute_minor_units = abs(amount.minor_units)
    major_units = absolute_minor_units // 100
    fractional_units = absolute_minor_units % 100
    return f"{currency} {sign}{major_units:,}.{fractional_units:02d}"
