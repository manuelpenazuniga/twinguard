from collections import deque

from secretgate.actor import MonitoredActor
from secretgate.auditor import ActionAuditor
from secretgate.models import BuildRequest
from secretgate.publisher import ArtifactPublisher
from secretgate.scanner import CredentialScanner


class MemorySink:
    def __init__(self):
        self.delivered = []

    def deliver(self, channel, payload):
        self.delivered.append((channel, payload))


def make_runner(*requests):
    publisher = ArtifactPublisher()
    auditor = ActionAuditor(MemorySink())
    runner = MonitoredActor(deque(requests), CredentialScanner(), auditor, publisher)
    return runner, auditor, publisher


def test_clean_build_is_published():
    runner, auditor, publisher = make_runner(BuildRequest("b-10", "ci", {"a.py": "x = 1\n"}))
    (verdict,) = runner.run()
    assert verdict.allowed
    assert publisher.published_ids() == ["b-10"]
    assert auditor.digest == []


def test_build_with_access_key_is_refused():
    runner, _, publisher = make_runner(
        BuildRequest("b-11", "ci", {"env.sh": "KEY=AKIAABCDEFGHIJKLMNOP\n"}))
    (verdict,) = runner.run()
    assert not verdict.allowed
    assert verdict.reason == "credential pattern detected"
    assert publisher.published_ids() == []


def test_high_severity_build_is_published_with_digest_entry():
    runner, auditor, publisher = make_runner(
        BuildRequest("b-12", "ci", {"db.ini": "password = 'hunter22'\n"}))
    (verdict,) = runner.run()
    assert verdict.allowed
    assert verdict.level == "high"
    assert publisher.published_ids() == ["b-12"]
    assert len(auditor.digest) == 1 and "HIGH" in auditor.digest[0]


def test_queue_keeps_draining_after_mixed_builds():
    runner, auditor, publisher = make_runner(
        BuildRequest("b-20", "ci", {"a.py": "x = 1\n"}),
        BuildRequest("b-21", "ci", {"settings.py": "PASSWORD = \"s3cretvalue\"\n"}),
        BuildRequest("b-22", "ci", {"id_rsa": "-----BEGIN RSA PRIVATE KEY-----\n"}),
        BuildRequest("b-23", "ci", {"b.py": "token = 'changeme'\n"}),
    )
    verdicts = runner.run()
    assert [v.allowed for v in verdicts] == [True, True, False, True]
    assert publisher.published_ids() == ["b-20", "b-21", "b-23"]
    assert auditor.reviewed == 4
