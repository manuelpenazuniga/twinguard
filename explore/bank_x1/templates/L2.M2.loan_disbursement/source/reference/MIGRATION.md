# Ledger gateway v1 -> v2

| v1                                          | v2                                              |
|---------------------------------------------|-------------------------------------------------|
| `post_transfer(account, amount_cents, memo)` | `submit(DisbursementInstruction(...))`          |
| returns a transaction id (`str`)            | returns `Receipt(reference, status)`            |
| no idempotency                              | `idempotency_key` (use the queue request id)    |
| always "booked"                             | `status` is `settled` or `pending`              |

`pending` means the ledger accepted the transfer and it settles in the next
treasury window. Treat it as a completed disbursement.

See `ledger_v2_handler.py` for the call pattern.
