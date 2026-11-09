"""Parsing and validation of queued bucket access change requests.

Messages on the ``bucket-acl-changes`` queue are JSON objects of the form::

    {"id": "req-0042", "bucket": "media-thumbnails",
     "public": true, "requested_by": "team-media"}
"""
import re
from dataclasses import dataclass

_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_REQUIRED = ("id", "bucket", "public", "requested_by")


class InvalidRequest(ValueError):
    """Raised when a queue message cannot be turned into an AccessChange."""


@dataclass(frozen=True)
class AccessChange:
    request_id: str
    bucket: str
    public: bool
    requested_by: str


def parse_request(message):
    """Validate a raw queue message and return an AccessChange."""
    if not isinstance(message, dict):
        raise InvalidRequest("message must be an object")
    missing = [key for key in _REQUIRED if key not in message]
    if missing:
        raise InvalidRequest(f"missing field(s): {', '.join(missing)}")
    bucket = message["bucket"]
    if not isinstance(bucket, str) or not _BUCKET_RE.match(bucket) or ".." in bucket:
        raise InvalidRequest(f"invalid bucket name: {bucket!r}")
    if not isinstance(message["public"], bool):
        raise InvalidRequest("field 'public' must be a boolean")
    request_id = str(message["id"]).strip()
    if not request_id:
        raise InvalidRequest("empty request id")
    return AccessChange(
        request_id=request_id,
        bucket=bucket,
        public=message["public"],
        requested_by=str(message["requested_by"]),
    )
