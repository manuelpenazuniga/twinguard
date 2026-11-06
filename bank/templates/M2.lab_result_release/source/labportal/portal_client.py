"""Client for the patient portal releases API (v2).

The v1 API exposed separate ``push_result`` and ``push_amendment`` calls. v2 accepts a
single ``ReleaseRequest`` on the ``/v2/releases`` endpoint for both final and amended
results and answers with a ``ReleaseReceipt``.
"""
from dataclasses import dataclass, field

RELEASE_KINDS = ("final", "amended")
RELEASES_ENDPOINT = "/v2/releases"


class PortalError(Exception):
    """The portal rejected a release."""


@dataclass(frozen=True)
class ReleaseRequest:
    patient_id: str
    accession: str
    kind: str = "final"
    payload: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in RELEASE_KINDS:
            raise ValueError(f"unknown release kind: {self.kind!r}")
        if not self.patient_id or not self.accession:
            raise ValueError("patient_id and accession are required")


@dataclass(frozen=True)
class ReleaseReceipt:
    release_id: str
    accession: str
    status: str  # "published", or "unchanged" when the portal already shows this version


class PortalClient:
    """Thin wrapper over an injected transport exposing ``send(method, path, body)``."""

    def __init__(self, transport):
        self._transport = transport

    def release(self, request):
        body = {
            "patient_id": request.patient_id,
            "accession": request.accession,
            "kind": request.kind,
            "payload": dict(request.payload),
        }
        response = self._transport.send("POST", RELEASES_ENDPOINT, body)
        if response.get("error"):
            raise PortalError(response["error"])
        return ReleaseReceipt(
            release_id=response["release_id"],
            accession=request.accession,
            status=response.get("status", "published"),
        )
