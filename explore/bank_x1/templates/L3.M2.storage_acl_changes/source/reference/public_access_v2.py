"""Reference implementation of a public-access update on the v2 access API.

Provided by the storage platform team as the pattern for moving callers off
``PutBucketAcl``. ``PutPublicAccessConfig`` takes an explicit access block and
a client token (used for idempotent retries) and answers with a ``ChangeId``
and a ``Status``. ``Unchanged`` means the bucket was already in the requested
state; callers treat it the same as ``Applied``.
"""
from acl import storage_api


def apply_public_access(transport, change):
    params = {
        "Bucket": change.bucket,
        "PublicAccess": {"Read": change.public, "Write": False},
        "ClientToken": change.request_id,
    }
    response = transport.call(storage_api.PUT_PUBLIC_ACCESS, params)
    storage_api.raise_for_error(storage_api.PUT_PUBLIC_ACCESS, response)
    storage_api.check_status(storage_api.PUT_PUBLIC_ACCESS, response)
    return {
        "request_id": change.request_id,
        "bucket": change.bucket,
        "status": "applied",
        "change_id": response["ChangeId"],
    }
