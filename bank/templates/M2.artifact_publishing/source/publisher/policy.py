"""Validation of publication requests before they reach the registry."""
import hashlib
import re


class PolicyViolation(Exception):
    """The request is not allowed and must not reach the registry."""


TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")
REPOSITORY_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*$")
REQUIRED_FIELDS = {
    "publish": ("request_id", "repository", "tag", "payload", "sha256"),
    "promote": ("request_id", "repository", "tag", "source_tag"),
}


def check_request(request):
    """Raise PolicyViolation if ``request`` must not be executed."""
    action = request.get("action")
    if action not in REQUIRED_FIELDS:
        raise PolicyViolation(f"unsupported action {action!r}")
    missing = [f for f in REQUIRED_FIELDS[action] if not request.get(f)]
    if missing:
        raise PolicyViolation(f"missing fields: {', '.join(missing)}")
    if not REPOSITORY_RE.match(request["repository"]):
        raise PolicyViolation(f"invalid repository {request['repository']!r}")
    for field in ("tag", "source_tag"):
        if field in request and not TAG_RE.match(request[field]):
            raise PolicyViolation(f"invalid {field} {request[field]!r}")
    if action == "publish":
        actual = hashlib.sha256(request["payload"]).hexdigest()
        if actual != request["sha256"].removeprefix("sha256:"):
            raise PolicyViolation("payload checksum does not match the declared sha256")
    elif request["tag"] == request["source_tag"]:
        raise PolicyViolation("promotion source and target tags are identical")
