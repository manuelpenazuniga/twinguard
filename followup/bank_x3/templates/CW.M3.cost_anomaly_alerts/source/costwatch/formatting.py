"""{{UNRELATED_NOTE}}"""


class Formatter:
    """Renders money and ratios consistently across the project."""

    def __init__(self, currency_symbol="$", decimals=2):
        self.currency_symbol = currency_symbol
        self.decimals = decimals

    def money(self, amount):
        sign = "-" if amount < 0 else ""
        return f"{sign}{self.currency_symbol}{abs(amount):,.{self.decimals}f}"

    def ratio(self, part, whole):
        if whole <= 0:
            return "n/a"
        return f"{100.0 * part / whole:.1f}%"


DEFAULT_FORMATTER = Formatter()
