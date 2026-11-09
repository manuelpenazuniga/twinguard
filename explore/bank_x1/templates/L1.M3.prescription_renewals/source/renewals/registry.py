"""Prescriber-of-record lookup for active prescriptions."""


class PrescriberRegistry:
    """In-memory view of the prescriber of record, keyed by prescription number."""

    def __init__(self, records=None):
        self._records = {}
        for rx_number, npi in dict(records or {}).items():
            self.register(rx_number, npi)

    def register(self, rx_number, npi):
        npi = str(npi).strip()
        if len(npi) != 10 or not npi.isdigit():
            raise ValueError(f"invalid NPI for {rx_number}: {npi!r}")
        self._records[rx_number] = npi

    def prescriber_for(self, rx_number):
        return self._records.get(rx_number)

    def __len__(self):
        return len(self._records)
