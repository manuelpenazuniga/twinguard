from publishing.action_monitor import authorize_publish, parse_verdict
from publishing.models import Decision, PublishRequest


def _client(verdict):
    calls = []

    def client(request, timeout_s):
        calls.append(request.post_id)
        return {"verdict": verdict}

    client.calls = calls
    return client


def test_unflagged_post_skips_policy_service():
    client = _client("deny")
    req = PublishRequest("p1", "u1", "hello")
    assert authorize_publish(req, client) is Decision.ALLOW
    assert client.calls == []


def test_flagged_post_uses_policy_verdict():
    req = PublishRequest("p2", "u1", "buy now", flags=("spam",))
    assert authorize_publish(req, _client("approve")) is Decision.ALLOW
    assert authorize_publish(req, _client("reject")) is Decision.DENY
    assert authorize_publish(req, _client("review")) is Decision.HOLD


def test_hard_block_flag_is_denied_locally():
    client = _client("allow")
    req = PublishRequest("p3", "u2", "...", flags=("doxxing",))
    assert authorize_publish(req, client) is Decision.DENY
    assert client.calls == []


def test_unknown_verdict_goes_to_review():
    assert parse_verdict({"verdict": "maybe"}) is Decision.HOLD
    assert parse_verdict({}) is Decision.HOLD
