"""Handlers that apply queued schema migration requests to the warehouse."""
from .bus import ADD_COLUMN, CHANGE_APPLIED, DROP_COLUMN, DROP_TABLE
from .jobs import JobResult


def _quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


class TargetRunner:
    def __init__(self, bus, executor):
        self._bus = bus
        self._executor = executor

    def register(self):
        self._bus.subscribe(DROP_COLUMN, self.drop_column)
        self._bus.subscribe(DROP_TABLE, self.drop_table)
        self._bus.subscribe(ADD_COLUMN, self.add_column)

    def drop_column(self, request):
        sql = (f"ALTER TABLE {_quote(request.table)} "
               f"DROP COLUMN IF EXISTS {_quote(request.column)}")
        self._executor.execute(sql)
        self._bus.publish(CHANGE_APPLIED, request)
        return JobResult(request.change_id, "applied", sql)

    def drop_table(self, request):
        sql = f"DROP TABLE IF EXISTS {_quote(request.table)}"
        self._executor.execute(sql)
        self._bus.publish(CHANGE_APPLIED, request)
        return JobResult(request.change_id, "applied", sql)

    def add_column(self, request):
        sql = (f"ALTER TABLE {_quote(request.table)} "
               f"ADD COLUMN {_quote(request.column)} {request.column_type or 'TEXT'}")
        self._executor.execute(sql)
        return JobResult(request.change_id, "applied", sql)
