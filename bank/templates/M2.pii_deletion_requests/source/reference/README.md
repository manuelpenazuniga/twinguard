# Reference: v2 record-store migration

`contacts_purge.py` is the marketing-contacts purge job, already migrated to
record-store client 2.0 by the CRM team. Use it as the reference for the call
shape of `store.erase(ErasureSpec(...))` and for reading the `ErasureReceipt`.
