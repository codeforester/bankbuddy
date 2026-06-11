from bankbuddy.accounts import masked_account_number


def test_masked_account_number_shows_only_suffix() -> None:
    assert masked_account_number("123456789") == "...6789"
    assert masked_account_number("123") == "...123"
