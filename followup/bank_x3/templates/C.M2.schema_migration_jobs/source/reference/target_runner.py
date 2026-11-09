"""Reference port of the job handlers to the warehouse v2 client.

Prepared by the warehouse team while upgrading the client; it shows the
``DdlStatement`` / ``apply()`` calling convention and the ``noop`` status for
drops whose target is already gone.
"""
from migrator.bus import ADD_COLUMN, DROP_COLUMN, DROP_TABLE
from migrator.jobs import JobResult
from migrator.warehouse import DdlStatement


class TargetRunner:
    def __init__(self, bus, executor):
        self._bus = bus
        self._executor = executor

    def register(self):
        self._bus.subscribe(DROP_COLUMN, self.drop_column)
        self._bus.subscribe(DROP_TABLE, self.drop_table)
        self._bus.subscribe(ADD_COLUMN, self.add_column)

    def drop_column(self, request):
        result = self._executor.apply(
            DdlStatement("drop_column", request.table, request.column))
        return _job_result(request, result)

    def drop_table(self, request):
        result = self._executor.apply(DdlStatement("drop_table", request.table))
        return _job_result(request, result)

    def add_column(self, request):
        result = self._executor.apply(DdlStatement(
            "add_column", request.table, request.column, request.column_type or "TEXT"))
        return _job_result(request, result)


def _job_result(request, result):
    status = "applied" if result.applied else "noop"
    return JobResult(request.change_id, status, result.statement.describe())
