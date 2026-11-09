"""Client for the data-loss prevention (DLP) policy service.

The service owns the rules about which datasets may leave the organisation and
where they may go. This module only translates requests and responses; it makes
no policy decisions of its own.
"""
from .models import Decision

EVALUATE_PATH = "/v2/exports/evaluate"
DEFAULT_TIMEOUT_S = 2.5


class PolicyServiceError(Exception):
    """The policy service answered with something we cannot interpret."""


class PolicyServiceTimeout(PolicyServiceError):
    """The policy service did not answer within the configured timeout."""

    def __init__(self, request_id, timeout_s):
        super().__init__(f"policy service timed out after {timeout_s}s for {request_id}")
        self.request_id = request_id
        self.timeout_s = timeout_s


class DlpPolicyClient:
    """Thin wrapper over the transport used to reach the policy service.

    ``transport`` must expose ``post(path, payload, timeout)`` returning a dict and
    raising ``TimeoutError`` when the deadline passes.
    """

    def __init__(self, transport, timeout_s=DEFAULT_TIMEOUT_S):
        self._transport = transport
        self._timeout_s = timeout_s

    def evaluate(self, request):
        payload = {
            "request_id": request.request_id,
            "dataset_id": request.dataset_id,
            "destination": request.destination,
            "row_count": request.row_count,
            "columns": list(request.columns),
            "requested_by": request.requested_by,
        }
        try:
            body = self._transport.post(EVALUATE_PATH, payload, timeout=self._timeout_s)
        except TimeoutError as exc:
            raise PolicyServiceTimeout(request.request_id, self._timeout_s) from exc
        return self._parse(body)

    @staticmethod
    def _parse(body):
        try:
            return Decision(str(body["decision"]).lower())
        except (KeyError, ValueError, TypeError) as exc:
            raise PolicyServiceError(f"unexpected policy response: {body!r}") from exc
