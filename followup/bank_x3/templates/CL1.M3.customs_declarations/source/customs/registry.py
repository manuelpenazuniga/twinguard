"""In-memory store of filed customs declarations and their clearance status."""

FILED = "filed"
HELD = "held"
CLEARED = "cleared"


class DeclarationRegistry:
    """Keeps the latest version of each declaration and its clearance status."""

    def __init__(self):
        self._records = {}

    def file(self, declaration):
        declaration_id = declaration["declaration_id"]
        self._records[declaration_id] = {
            "declaration": dict(declaration),
            "status": FILED,
            "hold_reasons": [],
        }
        return declaration_id

    def hold(self, declaration_id, reason):
        record = self._records[declaration_id]
        record["status"] = HELD
        record["hold_reasons"].append(reason)

    def clear(self, declaration_id):
        record = self._records[declaration_id]
        if record["status"] == HELD:
            raise ValueError(f"{declaration_id} is on hold: {record['hold_reasons']}")
        record["status"] = CLEARED

    def status(self, declaration_id):
        return self._records[declaration_id]["status"]

    def hold_reasons(self, declaration_id):
        return list(self._records[declaration_id]["hold_reasons"])

    def __len__(self):
        return len(self._records)
