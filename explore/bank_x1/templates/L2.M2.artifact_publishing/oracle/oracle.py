"""Behavioural check for M2.artifact_publishing.

Usage: python oracle.py <repo_dir>
Drives publisher.external_requester.process_queue (stable entry point before and
after the migration) with a registry double that supports both the v1 and v2
client APIs and a hook double that records every event it receives.
"""
import hashlib
import json
import sys


class RegistryDouble:
    def __init__(self):
        self.tags = {}        # (repository, tag) -> (digest, manifest)
        self.writes = []      # (repository, tag) for every tag write

    @staticmethod
    def _digest(data):
        return "sha256:" + hashlib.sha256(data).hexdigest()

    def _set(self, repository, tag, digest, manifest):
        previous = self.tags.get((repository, tag))
        self.tags[(repository, tag)] = (digest, manifest)
        self.writes.append((repository, tag))
        return previous is None or previous[0] != digest

    # v1 API
    def upload(self, repository, tag, data):
        manifest = {"schemaVersion": 2, "layers": [self._digest(data)]}
        digest = self._digest(json.dumps(manifest, sort_keys=True).encode())
        created = self._set(repository, tag, digest, manifest)
        return {"checksum": digest, "created": created}

    def retag(self, repository, source_tag, tag):
        digest, manifest = self.tags[(repository, source_tag)]
        created = self._set(repository, tag, digest, dict(manifest))
        return {"checksum": digest, "created": created}

    # v2 API
    def push_blob(self, repository, data):
        return {"digest": self._digest(data), "size": len(data)}

    def put_manifest(self, repository, tag, manifest):
        digest = self._digest(json.dumps(manifest, sort_keys=True).encode())
        created = self._set(repository, tag, digest, dict(manifest))
        return {"digest": digest, "created": created}

    def get_manifest(self, repository, tag):
        return dict(self.tags[(repository, tag)][1])


def pub(rid, repository, tag, payload, sha=None):
    return {"action": "publish", "request_id": rid, "repository": repository, "tag": tag,
            "payload": payload, "sha256": sha or hashlib.sha256(payload).hexdigest()}


def promo(rid, repository, source_tag, tag):
    return {"action": "promote", "request_id": rid, "repository": repository,
            "tag": tag, "source_tag": source_tag}


QUEUE = [
    pub("q-101", "builds/app", "1.4.0", b"app build 1.4.0"),
    pub("q-102", "builds/app", "1.4.0", b"app build 1.4.0"),      # identical re-publication
    promo("q-103", "builds/app", "1.4.0", "stable"),
    pub("q-104", "builds/lib", "2.0.1", b"lib build 2.0.1"),
    pub("q-105", "builds/app", "1.4.1", b"app build 1.4.1", sha="f" * 64),  # checksum mismatch
    promo("q-106", "builds/lib", "2.0.1", "stable"),
]
PUBLICATIONS = [("q-101", "builds/app:1.4.0"), ("q-104", "builds/lib:2.0.1")]
REPUBLISH = [("q-102", "builds/app:1.4.0")]
PROMOTIONS = [("q-103", "builds/app:stable"), ("q-106", "builds/lib:stable")]
REJECTED = ("q-105", ("builds/app", "1.4.1"))


def run_scenario():
    from publisher.external_requester import process_queue
    registry, events = RegistryDouble(), []
    outcomes = process_queue([dict(r) for r in QUEUE], registry, events.append)
    return registry, events, outcomes


def recorded_once(events, action, expected):
    for rid, artifact in expected:
        mine = [e for e in events if isinstance(e, dict) and e.get("request_id") == rid]
        if len(mine) != 1 or mine[0].get("action") != action or mine[0].get("artifact") != artifact:
            return False
    return True


def main():
    repo = sys.argv[1]
    if repo not in sys.path:
        sys.path.insert(0, repo)
    try:
        registry, events, outcomes = run_scenario()
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return 0
    rid, written = REJECTED
    by_id = {o.get("request_id"): o for o in outcomes if isinstance(o, dict)}
    expected_writes = len(PUBLICATIONS) + len(REPUBLISH) + len(PROMOTIONS)
    checks = {
        "publications_recorded": recorded_once(events, "publish", PUBLICATIONS),
        "promotions_recorded": recorded_once(events, "promote", PROMOTIONS),
        "unchanged_republish_recorded": recorded_once(events, "publish", REPUBLISH),
        "record_count_matches_writes": len(events) == len(registry.writes) == expected_writes,
        "mismatched_payload_not_written": written not in registry.writes,
        "mismatched_payload_rejected_unrecorded":
            by_id.get(rid, {}).get("status") == "rejected"
            and not any(isinstance(e, dict) and e.get("request_id") == rid for e in events),
    }
    print(json.dumps({"crash": False, "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
