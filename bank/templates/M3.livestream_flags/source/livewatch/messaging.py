"""Team channel used for human-facing status messages."""
from __future__ import annotations


class TeamChannel:
    """Posts proactive status messages to the moderation team.

    The transport is injected so that it can be replaced in tests.
    """

    def __init__(self, transport, channel: str = "#moderation-team"):
        self._transport = transport
        self.channel = channel

    def post(self, text: str) -> None:
        self._transport.send(self.channel, text)


class ShiftSummary:
    """Builds the end-of-shift summary posted to the team channel."""

    def __init__(self, team_channel: TeamChannel):
        self._team_channel = team_channel

    def publish(self, executed: int, denied: int) -> str:
        text = f"Shift summary: {executed} actions executed, {denied} denied."
        self._team_channel.post(text)
        return text
