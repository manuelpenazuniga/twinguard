"""Policy gate for outbound dataset exports.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Every export request taken from the queue is reviewed here before the
ExternalExecutor is allowed to copy any data outside the organisation. The
decision itself belongs to the DLP policy service; this class asks for it and
applies the local guard rails that must hold regardless of the service.
"""
import logging

from .models import Decision

log = logging.getLogger(__name__)

ALLOWED_SCHEMES = frozenset({"s3", "sftp"})


class SafetyMonitor:
    """Reviews export requests against the DLP policy service."""

    def __init__(self, policy_client, allowed_schemes=ALLOWED_SCHEMES):
        self._policy = policy_client
        self._allowed_schemes = frozenset(allowed_schemes)

    def review_export(self, request):
        """Return the Decision for ``request``."""
        if request.scheme not in self._allowed_schemes:
            log.warning("export %s denied: unsupported destination %s",
                        request.request_id, request.destination)
            return Decision.DENY
        decision = self._policy.evaluate(request)
        log.info("export %s reviewed: %s", request.request_id, decision.value)
        return decision
