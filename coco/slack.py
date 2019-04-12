import requests


class SlackExporter:

    def __init__(self, webhook_url):
        self.url = webhook_url

    def send(self, msg, channel=None):
        data = {'text': msg}
        if channel:
            data['channel'] = channel
        r = requests.post(self.url, json=data)
