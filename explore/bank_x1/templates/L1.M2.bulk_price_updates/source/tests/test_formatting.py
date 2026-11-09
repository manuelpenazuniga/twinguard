from pricing.formatting import format_cents, format_delta


def test_format_cents():
    assert format_cents(1999) == "$19.99"
    assert format_cents(123456, "EUR") == "€1,234.56"
    assert format_cents(-5) == "-$0.05"


def test_format_delta():
    assert format_delta(2000, 1800) == "-$2.00 (10.0%)"
    assert format_delta(0, 100) == "+$1.00 (0.0%)"
