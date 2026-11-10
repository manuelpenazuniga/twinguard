"""Client for the screening policy service (sanctions / limits / velocity rules).

The service is owned by the compliance platform team. The desk only consumes
its verdicts; it never decides on its own whether a wire may be released.
"""
from .models import Decision

DEFAULT_TIMEOUT_S = 2.0

_VERDICTS = {
    "approve": Decision.ALLOW,
    "reject": Decision.DENY,
    "review": Decision.HOLD,
}


class ScreeningPolicyClient:
    """Thin wrapper over a transport callable.

    ``transport(payload, timeout)`` returns a dict such as
    ``{"verdict": "approve"}`` and raises ``TimeoutError`` when the service
    does not answer within ``timeout`` seconds.
    """

    def __init__(self, transport, timeout_s=DEFAULT_TIMEOUT_S):
        self._transport = transport
        self._timeout_s = timeout_s

    def screen(self, request):
        payload = {
            "reference": request.request_id,
            "debtor": request.debtor_account,
            "beneficiary": request.beneficiary_account,
            "beneficiary_name": request.beneficiary_name,
            "amount_minor": request.amount_minor,
            "currency": request.currency,
            "rail": request.rail.value,
        }
        response = self._transport(payload, timeout=self._timeout_s)
        verdict = str(response.get("verdict", "")).lower()
        if verdict not in _VERDICTS:
            raise ValueError(f"unknown verdict {verdict!r} for {request.request_id}")
        return _VERDICTS[verdict]
