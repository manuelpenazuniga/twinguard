"""In-memory registry of livestreams and their moderation state."""
from __future__ import annotations

from datetime import datetime

from livewatch.models import LiveStream


class StreamRegistry:
    """Keeps the current state of every known livestream."""

    def __init__(self, streams: list[LiveStream] | None = None):
        self._streams: dict[str, LiveStream] = {}
        for stream in streams or []:
            self.add(stream)

    def add(self, stream: LiveStream) -> None:
        self._streams[stream.stream_id] = stream

    def get(self, stream_id: str) -> LiveStream | None:
        return self._streams.get(stream_id)

    def live_streams(self) -> list[LiveStream]:
        return sorted((s for s in self._streams.values() if s.live), key=lambda s: s.stream_id)

    def flag(self, stream_id: str, review_deadline: datetime) -> None:
        stream = self._streams[stream_id]
        stream.flagged = True
        stream.review_deadline = review_deadline

    def end(self, stream_id: str) -> None:
        self._streams[stream_id].live = False
