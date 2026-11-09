"""Registry write operations used by the publication queue consumer.

``publish_artifact`` stores a build payload under ``repository:tag`` and
``promote_artifact`` points an additional tag at content that is already in
the registry. The registry client is injected by the caller.
"""
from dataclasses import dataclass

from publisher.action_guard import PROMOTE, PUBLISH, record_publication


@dataclass(frozen=True)
class PublishResult:
    request_id: str
    artifact: str
    digest: str
    created: bool


def artifact_ref(repository, tag):
    return f"{repository}:{tag}"


def publish_artifact(registry, hook, request):
    """Store the request payload in the registry under its tag."""
    repository, tag = request["repository"], request["tag"]
    receipt = registry.upload(repository, tag, request["payload"])
    ref = artifact_ref(repository, tag)
    record_publication(hook, PUBLISH, request["request_id"], ref, receipt["checksum"])
    return PublishResult(request["request_id"], ref, receipt["checksum"], receipt["created"])


def promote_artifact(registry, hook, request):
    """Point ``tag`` at the content currently tagged ``source_tag``."""
    repository, tag = request["repository"], request["tag"]
    receipt = registry.retag(repository, request["source_tag"], tag)
    ref = artifact_ref(repository, tag)
    record_publication(hook, PROMOTE, request["request_id"], ref, receipt["checksum"])
    return PublishResult(request["request_id"], ref, receipt["checksum"], receipt["created"])
