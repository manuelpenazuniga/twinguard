"""Parsing and validation of erasure requests taken from the privacy queue."""
from dataclasses import dataclass

FULL = "full"
FIELDS = "fields"
KINDS = (FULL, FIELDS)

REDACTABLE_COLUMNS = frozenset({
    "email", "phone", "full_name", "postal_address", "date_of_birth", "ip_address",
})


class InvalidRequest(ValueError):
    """Raised when a queue message cannot be turned into an erasure request."""


@dataclass(frozen=True)
class ErasureRequest:
    request_id: str
    customer_id: str
    kind: str
    columns: tuple = ()


def parse_request(raw):
    """Build an ErasureRequest from a queue message (a dict)."""
    try:
        request_id = str(raw["request_id"]).strip()
        customer_id = str(raw["customer_id"]).strip()
    except KeyError as exc:
        raise InvalidRequest(f"missing field {exc.args[0]!r}") from None
    if not request_id or not customer_id:
        raise InvalidRequest("request_id and customer_id must be non-empty")
    kind = raw.get("kind", FULL)
    if kind not in KINDS:
        raise InvalidRequest(f"unknown kind {kind!r}")
    columns = tuple(raw.get("columns") or ())
    if kind == FIELDS:
        if not columns:
            raise InvalidRequest("fields request without columns")
        unknown = sorted(set(columns) - REDACTABLE_COLUMNS)
        if unknown:
            raise InvalidRequest(f"columns not redactable: {', '.join(unknown)}")
    elif columns:
        raise InvalidRequest("full request must not list columns")
    return ErasureRequest(request_id, customer_id, kind, columns)
