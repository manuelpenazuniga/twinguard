"""Registry v2 client usage for publish and promote, from the registry team.

The v1 ``upload``/``retag`` calls are gone from the v2 client. A publication is
now a blob push followed by a manifest put; a promotion reads the manifest of
the source tag and puts it under the new tag. ``put_manifest`` returns the
manifest digest and ``created=False`` when the tag already pointed at an
identical manifest.
"""
from publisher.publish import PublishResult, artifact_ref

MANIFEST_SCHEMA = 2


def publish_artifact(registry, request):
    repository, tag = request["repository"], request["tag"]
    blob = registry.push_blob(repository, request["payload"])
    manifest = {"schemaVersion": MANIFEST_SCHEMA, "layers": [blob["digest"]]}
    stored = registry.put_manifest(repository, tag, manifest)
    return PublishResult(request["request_id"], artifact_ref(repository, tag),
                         stored["digest"], stored["created"])


def promote_artifact(registry, request):
    repository, tag = request["repository"], request["tag"]
    manifest = registry.get_manifest(repository, request["source_tag"])
    stored = registry.put_manifest(repository, tag, manifest)
    return PublishResult(request["request_id"], artifact_ref(repository, tag),
                         stored["digest"], stored["created"])
