import pytest

from customs.tariff_format import format_customs_value, hs_chapter, normalise_hs_code


def test_normalise_hs_code():
    assert normalise_hs_code("27101245") == "2710.12"
    assert normalise_hs_code("8507.60") == "8507.60"
    assert hs_chapter("3604 10") == "36"


def test_short_hs_code_rejected():
    with pytest.raises(ValueError):
        normalise_hs_code("27")


def test_format_customs_value():
    assert format_customs_value(12345.675, "eur") == "12,345.68 EUR"
