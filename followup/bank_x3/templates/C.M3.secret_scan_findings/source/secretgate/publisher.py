"""In-memory artifact store used by the release pipeline."""


class ArtifactPublisher:
    """Stores the files of each published build under its build id."""

    def __init__(self):
        self.artifacts = {}

    def publish_artifact(self, request):
        if request.build_id in self.artifacts:
            raise ValueError(f"build {request.build_id} already published")
        self.artifacts[request.build_id] = dict(request.files)
        return request.build_id

    def published_ids(self):
        return sorted(self.artifacts)
