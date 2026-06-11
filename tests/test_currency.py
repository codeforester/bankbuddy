import pytest

from bankbuddy.currency import CurrencyAmount, format_amount, parse_amount


def test_parse_usd_and_inr_amounts_to_minor_units() -> None:
    assert parse_amount("$1,234.56", "USD") == CurrencyAmount("USD", 123456)
    assert parse_amount("₹1,234.50", "INR") == CurrencyAmount("INR", 123450)
    assert parse_amount("-42.05", "USD") == CurrencyAmount("USD", -4205)


def test_format_minor_units_with_currency_code() -> None:
    assert format_amount(CurrencyAmount("USD", 123456)) == "USD 1,234.56"
    assert format_amount(CurrencyAmount("INR", -4205)) == "INR -42.05"


def test_rejects_unknown_currency() -> None:
    with pytest.raises(ValueError, match="Unsupported currency: EUR"):
        parse_amount("10.00", "EUR")
