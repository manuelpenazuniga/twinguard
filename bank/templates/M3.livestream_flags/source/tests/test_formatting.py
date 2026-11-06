from datetime import timedelta

from livewatch.formatting import Formatter
from livewatch.messaging import ShiftSummary, TeamChannel


class RecordingTransport:
    def __init__(self):
        self.sent = []

    def send(self, channel, text):
        self.sent.append((channel, text))


def test_duration_formats():
    f = Formatter()
    assert f.duration(timedelta(seconds=42)) == "42s"
    assert f.duration(timedelta(minutes=3, seconds=5)) == "3m05s"
    assert f.duration(timedelta(hours=2, minutes=7)) == "2h07m"
    assert f.duration(timedelta(minutes=-10)) == "-10m00s"


def test_stream_label():
    assert Formatter().stream_label("ls-9", "heidi") == "ls-9 (heidi)"


def test_shift_summary_posts_to_team_channel():
    transport = RecordingTransport()
    text = ShiftSummary(TeamChannel(transport)).publish(executed=4, denied=1)
    assert transport.sent == [("#moderation-team", text)]
