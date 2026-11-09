"""Request and result records exchanged through the migration queue."""
from dataclasses import dataclass

DESTRUCTIVE_KINDS = ("drop_column", "drop_table")


@dataclass(frozen=True)
class MigrationRequest:
    change_id: str
    kind: str
    table: str
    column: str | None = None
    column_type: str | None = None
    ticket: str | None = None

    @property
    def destructive(self):
        return self.kind in DESTRUCTIVE_KINDS


@dataclass(frozen=True)
class JobResult:
    change_id: str
    status: str
    detail: str = ""
