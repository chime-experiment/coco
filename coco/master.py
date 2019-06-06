"""
coco master module.

This is the core of coco. Endpoints are loaded and called through the master module.
Also loads the config.
"""
import datetime
import os
import yaml

from comet import Manager, CometError

from . import Endpoint
from . import SlackExporter
from . import __version__


class Master:
    """
    The core module.

    Loads and keeps the config and endpoints. Endpoints are called through this module.
    """

    def __init__(self, config_path):
        config = self._load_config(config_path)
        self.slacker = SlackExporter(self.slack_url)
        config["endpoints"] = self._load_endpoints()
        self._register_config(config)

    def call_endpoint(self, name):
        """
        Call an endpoint.

        Parameters
        ----------
        name : str
            Name of the endpoint

        Returns
        -------
        :class:`Result`
            The result of the endpoint call.

        """
        self.endpoints[name].call()

    def _register_config(self, config):
        # Register config with comet broker
        try:
            enable_comet = config["comet_broker"]["enabled"]
        except KeyError:
            print("Missing config value 'comet_broker/enabled'.")
            exit(1)
        if enable_comet:
            try:
                comet_host = config["comet_broker"]["host"]
                comet_port = config["comet_broker"]["port"]
            except KeyError as exc:
                print(
                    "Failure registering initial config with comet broker: 'comet_broker/{}' "
                    "not defined in config.".format(exc[0])
                )
                exit(1)
            comet = Manager(comet_host, comet_port)
            try:
                comet.register_start(datetime.datetime.utcnow(), __version__)
                comet.register_config(config)
            except CometError as exc:
                print("Comet failed registering CoCo startup and initial config: {}".format(exc))
                exit(1)
        else:
            self.log.warning("Config registration DISABLED. This is only OK for testing.")

    def _load_config(self, config_path):
        with open(config_path, "r") as stream:
            try:
                config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)

        self.endpoint_dir = config["endpoint_dir"]
        try:
            self.slack_url = config["slack_webhook"]
        except KeyError:
            self.slack_url = None
            print("Key 'slack_webhook' not found. Slack messaging DISABLED.")
        return config

    def _load_endpoints(self):
        self.endpoints = dict()
        endpoint_conf = list()
        for endpoint_file in os.listdir(self.endpoint_dir):
            # Only accept files ending in .conf as endpoint configs.
            # Endpoint config files starting with an underscore (_) are disabled.
            if endpoint_file.endswith(".conf") and not endpoint_file.startswith("_"):

                # Remove .conf from the config file name to get the name of the endpoint
                name = os.path.splitext(endpoint_file)[0]

                with open(os.path.join(self.endpoint_dir, endpoint_file), "r") as stream:
                    try:
                        conf = yaml.safe_load(stream)
                    except yaml.YAMLError as exc:
                        print(exc)

                # Create the endpoint object
                self.endpoints[name] = Endpoint(
                    name, conf, self.endpoint_callback, self.slacker, self
                )
                conf["name"] = name
                endpoint_conf.append(conf)
        return endpoint_conf

    def endpoint_callback(self, name):
        """
        Tell the master that an endpoint was called.

        Parameters
        ----------
        name : str
            The name of the endpoint.
        """
        print("{} just called".format(name))
