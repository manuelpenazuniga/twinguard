from surveil.textfmt import format_percent, format_quantity


def test_format_quantity():
    assert format_quantity(1234567) == "1,234,567"
    assert format_quantity(-1500) == "-1,500"


def test_format_percent():
    assert format_percent(0.854) == "85.4%"
