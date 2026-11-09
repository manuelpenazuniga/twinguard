"""Engineering-unit formatting helpers.

{{UNRELATED_NOTE}}
"""

SYMBOLS = {"degC": "°C", "bar": "bar", "rpm": "rpm", "pct": "%", "m3h": "m³/h"}


def fmt_value(value, unit, digits=1):
    symbol = SYMBOLS.get(unit, unit)
    return f"{value:.{digits}f} {symbol}"


def percent(part, whole):
    if whole == 0:
        return "n/a"
    return f"{100.0 * part / whole:.0f}%"


def to_celsius(value_f):
    return (value_f - 32.0) * 5.0 / 9.0
