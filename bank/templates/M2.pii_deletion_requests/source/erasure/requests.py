"""Parsing of deletion-request queue messages."""
from dataclasses import dataclass

REQUIRED_FIELDS = ("request_id", "customer_id", "tables", "reason")


@dataclass(frozen=True)
class ErasureRequest:
    request_id: str
    customer_id: str
    tables: tuple[str, ...]
    reason: str
    identity_verified: bool
    submitted_by: str


def parse_request(message):
    """Build an ErasureRequest from a raw queue message (a dict).

    Raises ValueError when a required field is missing or malformed.
    """
    missing = [name for name in REQUIRED_FIELDS if not message.get(name)]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    tables = message["tables"]
    if isinstance(tables, str):
        tables = [part.strip() for part in tables.split(",") if part.strip()]
    if not tables:
        raise ValueError("no tables requested")
    return ErasureRequest(
        request_id=str(message["request_id"]),
        customer_id=str(message["customer_id"]),
        tables=tuple(sorted(set(tables))),
        reason=str(message["reason"]),
        identity_verified=bool(message.get("identity_verified", False)),
        submitted_by=str(message.get("submitted_by", "unknown")),
    )
