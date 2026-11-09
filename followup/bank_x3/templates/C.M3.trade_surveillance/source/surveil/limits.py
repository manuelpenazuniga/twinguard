"""Per-account position limits and the running position book."""
from collections import defaultdict


class LimitNotConfigured(KeyError):
    pass


class PositionBook:
    """Tracks net positions per (account, symbol) and the configured limits."""

    def __init__(self, limits, warning_ratio=0.8):
        if not 0 < warning_ratio < 1:
            raise ValueError("warning_ratio must be between 0 and 1")
        self._limits = dict(limits)
        self._positions = defaultdict(int)
        self.warning_ratio = warning_ratio

    def limit_for(self, account, symbol):
        key = (account, symbol)
        if key in self._limits:
            return self._limits[key]
        if (account, "*") in self._limits:
            return self._limits[(account, "*")]
        raise LimitNotConfigured(f"no position limit for {account}/{symbol}")

    def position(self, account, symbol):
        return self._positions[(account, symbol)]

    def projected(self, order):
        return self.position(order.account, order.symbol) + order.signed_quantity()

    def apply(self, order):
        self._positions[(order.account, order.symbol)] += order.signed_quantity()
        return self._positions[(order.account, order.symbol)]
