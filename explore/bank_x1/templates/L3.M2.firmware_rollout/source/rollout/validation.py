"""Admission checks applied to rollout requests before anything reaches the fleet."""

REQUIRED_FIELDS = ("request_id", "group", "version")


class RejectedRequest(Exception):
    def __init__(self, request_id, reason):
        super().__init__(f"{request_id}: {reason}")
        self.request_id = request_id
        self.reason = reason


def check_request(request, catalog):
    """Raise RejectedRequest unless the request may be sent to the fleet."""
    missing = [name for name in REQUIRED_FIELDS if not request.get(name)]
    if missing:
        raise RejectedRequest(request.get("request_id"), "missing " + ", ".join(missing))
    if request.get("kind") == "push":
        if not catalog.is_approved(request["version"], request.get("image")):
            raise RejectedRequest(request["request_id"], "image not approved for release")
