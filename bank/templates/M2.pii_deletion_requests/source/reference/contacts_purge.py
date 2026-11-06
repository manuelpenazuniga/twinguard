"""Marketing-contacts purge job, migrated to record-store client 2.0."""
from erasure.store_api import ErasureSpec


def purge_contact(store, request):
    """Purge one contact's marketing data; return rows removed."""
    spec = ErasureSpec(
        customer_id=request.customer_id,
        tables=tuple(request.tables),
        reason=request.reason,
    )
    receipt = store.erase(spec)
    return receipt.rows_erased


def purge_batch(store, requests):
    """Purge a batch of contacts; return {customer_id: rows_removed}."""
    return {request.customer_id: purge_contact(store, request) for request in requests}
