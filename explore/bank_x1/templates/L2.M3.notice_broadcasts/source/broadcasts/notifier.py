"""Automatic notifier that posts monitor alerts to chat channels."""


class ChannelNotifier:
    """Formats alert payloads and hands them to a chat client.

    ``client`` must provide ``post(channel, text)``.
    """

    def __init__(self, client):
        self.client = client
        self.sent = []

    def send(self, channel, payload):
        text = "{level} {severity} [{rule}] job={job_id}: {detail}".format(**payload)
        self.client.post(channel, text)
        self.sent.append((channel, payload))
