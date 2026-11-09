"""Mail transfer clients.

``MtaClient`` is the current submission API: one ``Envelope`` in, one ``Receipt`` out.
``SmtpPool`` is the legacy pooled client. It is being retired; relay deployments now
inject an ``MtaClient`` only.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Envelope:
    ref: str
    sender: str
    recipients: tuple[str, ...]
    payload: str


@dataclass(frozen=True)
class Receipt:
    ref: str
    queue_id: str
    status: str  # "queued" or "deferred"


class MtaClient:
    """Client for the MTA submission endpoint (v2)."""

    def __init__(self, connection):
        self._connection = connection

    def submit(self, envelope: Envelope) -> Receipt:
        if not envelope.recipients:
            raise ValueError("envelope has no recipients")
        reply = self._connection.post("/v2/submit", {
            "ref": envelope.ref,
            "mail_from": envelope.sender,
            "rcpt_to": list(envelope.recipients),
            "data": envelope.payload,
        })
        return Receipt(ref=envelope.ref, queue_id=reply["queue_id"],
                       status=reply.get("status", "queued"))


class SmtpPool:
    """Legacy pooled SMTP client (deprecated, kept for old deployments)."""

    def __init__(self, connection):
        self._connection = connection

    def send(self, sender, recipients, message, ref):
        reply = self._connection.post("/v1/send", {
            "from": sender, "to": list(recipients), "message": message, "ref": ref,
        })
        return reply["queue_id"]
