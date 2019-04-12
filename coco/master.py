import yaml
import os

from . import Endpoint
from . import SlackExporter


class Master:

    def __init__(self, config_path):
        self._load_config(config_path)
        self.slacker = SlackExporter(self.slack_url)
        self._load_endpoints()

    def call_endpoint(self, name):
        self.endpoints[name].call()

    def _load_config(self, config_path):

        with open(config_path, 'r') as stream:
            try:
                config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)

        self.endpoint_dir = config['endpoint_dir']
        self.slack_url = config['slack_webhook']

    def _load_endpoints(self):
        self.endpoints = dict()
        for endpoint_file in os.listdir(self.endpoint_dir):
            # Only accept files ending in .conf as endpoint configs.
            # Endpoint config files starting with an underscore (_) are disabled.
            if endpoint_file.endswith('.conf') and not endpoint_file.startswith('_'):

                # Remove .conf from the config file name to get the name of the endpoint
                name = os.path.splitext(endpoint_file)[0]

                with open(os.path.join(self.endpoint_dir, endpoint_file), 'r') as stream:
                    try:
                        conf = yaml.safe_load(stream)
                    except yaml.YAMLError as exc:
                        print(exc)

                # Create the endpoint object
                self.endpoints[name] = Endpoint(name, conf, self.endpoint_callback, self.slacker,
                                                self)

    def endpoint_callback(self, name):
        print('{} just called'.format(name))
