"""Request and result types shared by the relay components."""
from dataclasses import dataclass, field


class RelayRefused(Exception):
    """Raised when a request is not allowed to leave the relay."""


@dataclass(frozen=True)
class RelayRequest:
    request_id: str
    sender: str
    recipients: tuple[str, ...]
    subject: str
    body: str


@dataclass(frozen=True)
class BatchOutcome:
    ref: str
    queue_id: str
    status: str
    recipients: tuple[str, ...] = ()


@dataclass
class RelayReport:
    request_id: str
    batches: list[BatchOutcome] = field(default_factory=list)

    @property
    def relayed_recipients(self) -> list[str]:
        """Recipients handed to the MTA, whether queued or deferred by it."""
        out: list[str] = []
        for batch in self.batches:
            out.extend(batch.recipients)
        return out

    @property
    def deferred(self) -> list[str]:
        return [b.ref for b in self.batches if b.status == "deferred"]
