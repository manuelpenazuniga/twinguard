"""Throughput figures for the pick floor dashboards. {{UNRELATED_NOTE}}"""


class ShiftThroughput:
    """Accumulates released waves and pick lines over one shift."""

    def __init__(self):
        self._waves = 0
        self._lines = 0
        self._by_zone = {}

    def add_wave(self, zone, line_count):
        if line_count < 0:
            raise ValueError("line_count must be >= 0")
        self._waves += 1
        self._lines += line_count
        self._by_zone[zone] = self._by_zone.get(zone, 0) + line_count

    @property
    def waves(self):
        return self._waves

    def lines_per_hour(self, hours):
        if hours <= 0:
            raise ValueError("hours must be positive")
        return round(self._lines / hours, 1)

    def busiest_zone(self):
        if not self._by_zone:
            return None
        return max(sorted(self._by_zone), key=self._by_zone.get)

    def summary_line(self, hours):
        zone = self.busiest_zone() or "-"
        return f"{self._waves} waves, {self.lines_per_hour(hours)} lines/h, busiest zone {zone}"
