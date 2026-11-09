"""Client for the hospital formulary policy service."""
from .models import PolicyVerdict, RestockOrder

DECISION_PATH = "/v2/formulary/restock-decisions"


class PolicyServiceError(Exception):
    """The formulary policy service returned an unusable response."""


class PolicyTimeout(PolicyServiceError):
    """The formulary policy service did not answer within the configured timeout."""

    def __init__(self, order_id: str, timeout_s: float):
        super().__init__(f"formulary decision for {order_id} timed out after {timeout_s}s")
        self.order_id = order_id
        self.timeout_s = timeout_s


class FormularyPolicyClient:
    """Asks the formulary service whether a restock order may be loaded.

    ``transport`` must provide ``post(path, payload, timeout)`` returning a dict
    and raising ``TimeoutError`` when the service does not answer in time.
    """

    def __init__(self, transport, timeout_s: float = 2.0):
        self._transport = transport
        self._timeout_s = timeout_s

    def evaluate(self, order: RestockOrder) -> PolicyVerdict:
        payload = {
            "order_id": order.order_id,
            "cabinet_id": order.cabinet_id,
            "unit": order.unit,
            "lines": [
                {"ndc": l.ndc, "quantity": l.quantity, "controlled": l.controlled}
                for l in order.lines
            ],
        }
        try:
            body = self._transport.post(DECISION_PATH, payload, timeout=self._timeout_s)
        except TimeoutError as exc:
            raise PolicyTimeout(order.order_id, self._timeout_s) from exc
        if not isinstance(body, dict) or "decision" not in body:
            raise PolicyServiceError(f"malformed response for {order.order_id}: {body!r}")
        return PolicyVerdict(code=str(body["decision"]).lower(), reason=str(body.get("reason", "")))
