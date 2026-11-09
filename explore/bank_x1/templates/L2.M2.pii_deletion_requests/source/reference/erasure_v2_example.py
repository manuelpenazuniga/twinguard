"""Minimal erasure job written against warehouse client 2.x."""


def erase_customer(client, customer_id):
    receipt = client.erase(customer_id)
    return {"customer_id": customer_id, "status": "completed",
            "rows": receipt.rows_affected, "erasure_id": receipt.erasure_id}


def redact_fields(client, customer_id, columns):
    receipt = client.erase(customer_id, columns=list(columns))
    return {"customer_id": customer_id, "status": "completed",
            "rows": receipt.rows_affected, "erasure_id": receipt.erasure_id}
