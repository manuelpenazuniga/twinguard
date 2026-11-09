"""Pick path sequencing inside a zone."""


class LocationError(ValueError):
    """Raised for a location code that does not follow ``<aisle>-<bay>-<level>``."""


class SerpentineRouter:
    """Orders pick lines along a serpentine (S-shaped) walk through the aisles.

    Aisles are visited in ascending order. Odd-numbered aisles are walked with
    ascending bays, even-numbered aisles with descending bays, so the picker never
    walks back to the aisle head. Within a bay, lower levels come first.
    """

    def sequence(self, lines):
        return tuple(sorted(lines, key=self._key))

    def _key(self, line):
        aisle, bay, level = self.parse(line.location)
        walk_bay = bay if aisle % 2 == 1 else -bay
        return (aisle, walk_bay, level, line.sku)

    @staticmethod
    def parse(location):
        parts = location.split("-")
        if len(parts) != 3 or not parts[0][:1].isalpha():
            raise LocationError(f"bad location code: {location!r}")
        try:
            return int(parts[0][1:]), int(parts[1]), int(parts[2])
        except ValueError:
            raise LocationError(f"bad location code: {location!r}") from None

    def walk_length(self, lines):
        """Number of aisle changes plus bay steps along the routed sequence."""
        steps = 0
        previous = None
        for line in self.sequence(lines):
            aisle, bay, _ = self.parse(line.location)
            if previous is not None:
                steps += abs(aisle - previous[0]) + (abs(bay - previous[1]) if aisle == previous[0] else 0)
            previous = (aisle, bay)
        return steps
