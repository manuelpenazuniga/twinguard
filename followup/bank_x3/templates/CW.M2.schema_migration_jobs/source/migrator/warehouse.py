"""Warehouse DDL client, version 2.

Version 2.0 removed the string-based ``execute(sql)`` call. Callers now build a
``DdlStatement`` and pass it to ``apply()``, which returns a ``DdlResult``.
Drops are always ``IF EXISTS``: dropping something that is already gone is not
an error, ``DdlResult.applied`` is simply ``False``.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DdlStatement:
    op: str
    table: str
    column: str | None = None
    column_type: str | None = None

    def describe(self):
        target = self.table if self.column is None else f"{self.table}.{self.column}"
        return f"{self.op} {target}"


@dataclass(frozen=True)
class DdlResult:
    statement: DdlStatement
    applied: bool


class WarehouseExecutor:
    """Applies DDL statements to a catalog of ``{table: [columns]}``."""

    def __init__(self, catalog=None):
        self._catalog = {t: list(cols) for t, cols in (catalog or {}).items()}
        self.history = []

    def has_table(self, table):
        return table in self._catalog

    def columns(self, table):
        return list(self._catalog.get(table, []))

    def apply(self, statement):
        handler = getattr(self, "_" + statement.op, None)
        if handler is None:
            raise ValueError(f"unsupported DDL op {statement.op!r}")
        applied = handler(statement)
        self.history.append(statement)
        return DdlResult(statement, applied)

    def _drop_column(self, statement):
        cols = self._catalog.get(statement.table)
        if cols is None or statement.column not in cols:
            return False
        cols.remove(statement.column)
        return True

    def _drop_table(self, statement):
        return self._catalog.pop(statement.table, None) is not None

    def _add_column(self, statement):
        cols = self._catalog.get(statement.table)
        if cols is None:
            raise KeyError(f"unknown table {statement.table!r}")
        if statement.column in cols:
            return False
        cols.append(statement.column)
        return True
