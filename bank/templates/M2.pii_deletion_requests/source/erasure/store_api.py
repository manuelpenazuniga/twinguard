"""Types of the record-store client 2.0 erasure API.

Record-store client 2.0 replaced the v1 call

    store.delete_customer(customer_id, tables=[...], on_complete=callback)

with

    receipt = store.erase(ErasureSpec(customer_id=..., tables=(...), reason=...))

The v2 call is synchronous and returns an ErasureReceipt; there is no
completion callback any more. The v1 method was removed in 2.0.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ErasureSpec:
    customer_id: str
    tables: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ErasureReceipt:
    erasure_id: str
    customer_id: str
    rows_erased: int
