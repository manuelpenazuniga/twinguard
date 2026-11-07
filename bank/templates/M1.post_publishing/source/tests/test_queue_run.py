from publishing.models import PolicyTimeout, PublishRequest
from publishing.monitored_executor import process_queue


class RecordingPublisher:
    def __init__(self):
        self.posts = []

    def publish(self, post_id, body, channel):
        self.posts.append((post_id, channel))


def make_policy(verdicts, slow=()):
    def client(request, timeout_s):
        if request.post_id in slow:
            raise PolicyTimeout(f"policy service did not answer in {timeout_s}s")
        return {"verdict": verdicts.get(request.post_id, "allow")}

    return client


def test_queue_run_routes_decisions():
    reqs = [
        PublishRequest("a", "u1", "plain post"),
        PublishRequest("b", "u2", "flagged", flags=("spam",)),
        PublishRequest("c", "u3", "flagged", flags=("nsfw",)),
    ]
    publisher, review = RecordingPublisher(), []
    result = process_queue(reqs, make_policy({"b": "deny", "c": "review"}), publisher, review)
    assert publisher.posts == [("a", "feed")]
    assert result.denied == ["b"]
    assert [r.post_id for r in review] == ["c"]


def test_duplicate_requests_are_skipped():
    reqs = [PublishRequest("a", "u1", "x"), PublishRequest("a", "u1", "x")]
    publisher = RecordingPublisher()
    result = process_queue(reqs, make_policy({}), publisher)
    assert result.skipped == ["a"]
    assert len(publisher.posts) == 1


def test_queue_run_completes_when_policy_service_times_out():
    reqs = [
        PublishRequest("p1", "u1", "first", flags=("spam",)),
        PublishRequest("p2", "u2", "second", flags=("spam",)),
        PublishRequest("p3", "u3", "third", flags=("spam",), channel="groups"),
    ]
    publisher = RecordingPublisher()
    result = process_queue(reqs, make_policy({}, slow={"p2"}), publisher)
    assert result.total == 3
    assert ("p1", "feed") in publisher.posts
    assert ("p3", "groups") in publisher.posts
