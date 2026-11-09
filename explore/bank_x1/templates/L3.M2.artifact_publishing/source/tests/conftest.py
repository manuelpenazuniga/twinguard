import hashlib
import json

import pytest


class FakeRegistry:
    """In-memory registry exposing the v2 client interface."""

    def __init__(self):
        self.blobs = {}
        self.manifests = {}

    def push_blob(self, repository, data):
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        self.blobs[(repository, digest)] = data
        return {"digest": digest, "size": len(data)}

    def put_manifest(self, repository, tag, manifest):
        body = json.dumps(manifest, sort_keys=True).encode()
        digest = "sha256:" + hashlib.sha256(body).hexdigest()
        previous = self.manifests.get((repository, tag))
        self.manifests[(repository, tag)] = (digest, dict(manifest))
        return {"digest": digest, "created": previous is None or previous[0] != digest}

    def get_manifest(self, repository, tag):
        return dict(self.manifests[(repository, tag)][1])


@pytest.fixture
def registry():
    return FakeRegistry()


@pytest.fixture
def hook():
    return lambda event: None


def publish_request(request_id, repository, tag, payload, sha256=None):
    return {
        "action": "publish",
        "request_id": request_id,
        "repository": repository,
        "tag": tag,
        "payload": payload,
        "sha256": sha256 or hashlib.sha256(payload).hexdigest(),
    }


@pytest.fixture
def make_publish():
    return publish_request
