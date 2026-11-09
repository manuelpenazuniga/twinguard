"""Thin helpers around the storage control-plane transport.

The transport is any object with a ``call(operation, params)`` method that
returns the decoded JSON response as a dict. Production wires in the HTTP
transport from the platform SDK; tests pass in-memory fakes.
"""

# Operation names understood by the control plane.
LEGACY_PUT_ACL = "PutBucketAcl"
PUT_PUBLIC_ACCESS = "PutPublicAccessConfig"

# Canned ACLs accepted by the legacy operation.
CANNED_PUBLIC_READ = "public-read"
CANNED_PRIVATE = "private"

# Statuses returned by the v2 access API for a successful update.
STATUS_APPLIED = "Applied"
STATUS_UNCHANGED = "Unchanged"
OK_STATUSES = frozenset({STATUS_APPLIED, STATUS_UNCHANGED})


class StorageApiError(RuntimeError):
    """Raised when the control plane rejects an operation."""


def raise_for_error(operation, response):
    """Raise StorageApiError if the response carries an error block."""
    if not isinstance(response, dict):
        raise StorageApiError(f"{operation}: malformed response {response!r}")
    error = response.get("Error")
    if error:
        code = error.get("Code", "Unknown")
        message = error.get("Message", "")
        raise StorageApiError(f"{operation} failed: {code}: {message}".rstrip(": "))
    return response


def check_status(operation, response):
    """Validate the ``Status`` field of a v2 access API response."""
    status = response.get("Status")
    if status not in OK_STATUSES:
        raise StorageApiError(f"{operation}: unexpected status {status!r}")
    return status
