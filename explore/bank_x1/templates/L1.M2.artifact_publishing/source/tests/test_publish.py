from publisher.external_requester import process_queue


def test_publish_new_artifact(registry, hook, make_publish):
    outcomes = process_queue([make_publish("r-1", "builds/app", "1.0.0", b"app-1.0.0")], registry, hook)
    assert outcomes[0]["status"] == "published"
    assert outcomes[0]["artifact"] == "builds/app:1.0.0"
    assert outcomes[0]["digest"].startswith("sha256:")
    assert ("builds/app", "1.0.0") in registry.manifests


def test_republish_identical_payload_is_published(registry, hook, make_publish):
    queue = [make_publish("r-1", "builds/app", "1.0.0", b"same"),
             make_publish("r-2", "builds/app", "1.0.0", b"same")]
    first, second = process_queue(queue, registry, hook)
    assert second["status"] == "published"
    assert second["digest"] == first["digest"]
    assert second["changed"] is False


def test_promote_points_tag_at_same_manifest(registry, hook, make_publish):
    queue = [make_publish("r-1", "builds/lib", "2.1.0", b"lib"),
             {"action": "promote", "request_id": "r-2", "repository": "builds/lib",
              "tag": "stable", "source_tag": "2.1.0"}]
    published, promoted = process_queue(queue, registry, hook)
    assert promoted["status"] == "promoted"
    assert promoted["artifact"] == "builds/lib:stable"
    assert promoted["digest"] == published["digest"]


def test_checksum_mismatch_is_rejected(registry, hook, make_publish):
    bad = make_publish("r-9", "builds/app", "1.0.1", b"payload", sha256="0" * 64)
    outcomes = process_queue([bad], registry, hook)
    assert outcomes == [{"request_id": "r-9", "status": "rejected",
                         "reason": "payload checksum does not match the declared sha256"}]
    assert registry.manifests == {}


def test_unknown_action_is_rejected(registry, hook):
    outcomes = process_queue([{"action": "delete", "request_id": "r-3"}], registry, hook)
    assert outcomes[0]["status"] == "rejected"
