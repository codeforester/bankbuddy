import pytest

from bankbuddy import accounts
from bankbuddy.accounts import masked_account_number


def test_masked_account_number_shows_only_suffix() -> None:
    assert masked_account_number("123456789") == "...6789"
    assert masked_account_number("123") == "...123"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("US", "US"),
        ("usa", "US"),
        ("United States", "US"),
        ("United States of America", "US"),
        ("IN", "IN"),
        ("India", "IN"),
    ],
)
def test_normalize_country_code_accepts_supported_aliases(
    value: str,
    expected: str,
) -> None:
    assert accounts.normalize_country_code(value) == expected


def test_normalize_country_code_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="Unsupported country"):
        accounts.normalize_country_code("Atlantis")
