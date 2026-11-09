"""Applies queued public-access changes to storage buckets.

``process_requests`` is the entry point used by the queue consumer: it takes a
batch of raw messages from the ``bucket-acl-changes`` queue and returns one
result dict per message. The transport, the authorization check and the audit
hook are all injected.
"""
from acl import storage_api
from acl.requests import InvalidRequest, parse_request
from acl.watch_guard import record_access_change

RESULT_APPLIED = "applied"
RESULT_DENIED = "denied"
RESULT_INVALID = "invalid"


def _result(change, status, change_id=None):
    return {
        "request_id": change.request_id,
        "bucket": change.bucket,
        "status": status,
        "change_id": change_id,
    }


def apply_public_access(transport, change, audit_hook):
    """Set the bucket's public read access to the requested value."""
    acl = storage_api.CANNED_PUBLIC_READ if change.public else storage_api.CANNED_PRIVATE
    response = transport.call(storage_api.LEGACY_PUT_ACL, {"Bucket": change.bucket, "ACL": acl})
    storage_api.raise_for_error(storage_api.LEGACY_PUT_ACL, response)
    record_access_change(audit_hook, change)
    return _result(change, RESULT_APPLIED)


def handle_message(message, transport, authorize, audit_hook):
    """Validate, authorize and apply a single queue message."""
    try:
        change = parse_request(message)
    except InvalidRequest as exc:
        raw = message if isinstance(message, dict) else {}
        return {
            "request_id": raw.get("id"),
            "bucket": raw.get("bucket"),
            "status": RESULT_INVALID,
            "change_id": None,
            "reason": str(exc),
        }
    if not authorize(change):
        return _result(change, RESULT_DENIED)
    return apply_public_access(transport, change, audit_hook)


def process_requests(messages, transport, authorize, audit_hook):
    """Process a batch of queue messages in order and return their results."""
    return [handle_message(m, transport, authorize, audit_hook) for m in messages]
