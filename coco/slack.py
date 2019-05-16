"""
coco slack module.

Exports messages to slack.
"""
import requests


class SlackExporter:
    """Slack exporter: sends messages to slack."""

    def __init__(self, webhook_url):
        self.url = webhook_url

    def send(self, msg, channel=None):
        """
        Send a slack message.

        Parameters
        ----------
        msg : str
            The message.
        channel : str
            The slack channel (without `#`). Optional, default is implied in the Slack API token.
        """
        data = {"text": msg}
        if channel:
            data["channel"] = channel
        r = requests.post(self.url, json=data)
