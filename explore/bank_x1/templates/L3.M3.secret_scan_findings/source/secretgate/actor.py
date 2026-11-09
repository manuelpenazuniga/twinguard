"""Build runner that drains the build request queue."""


class MonitoredActor:
    """Takes builds from the request queue, scans them and publishes the allowed ones."""

    def __init__(self, queue, scanner, auditor, publisher):
        self.queue = queue
        self.scanner = scanner
        self.auditor = auditor
        self.publisher = publisher
        self.published = []
        self.rejected = []

    def process_next(self):
        request = self.queue.popleft()
        report = self.scanner.scan(request)
        verdict = self.auditor.review(report)
        if verdict.allowed:
            self.publisher.publish_artifact(request)
            self.published.append(request.build_id)
        else:
            self.rejected.append(verdict)
        return verdict

    def run(self):
        verdicts = []
        while self.queue:
            verdicts.append(self.process_next())
        return verdicts
