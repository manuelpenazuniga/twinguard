# Warehouse client 2.x – migration examples

Provided by the warehouse team. Client 2.x removes `delete_customer` and
`null_columns`; both are replaced by a single call:

```
receipt = client.erase(customer_id, columns=None)
receipt.rows_affected   # int, 0 when nothing was left to erase
receipt.erasure_id      # str, warehouse reference for the erasure
```

`columns=None` erases every row of the customer; a list of column names nulls
out only those columns. Callers should surface `erasure_id` in their result
records so support can trace tickets back to the warehouse.

See `erasure_v2_example.py` for a minimal job written against 2.x.
