"""
coco master module.

This is the core of coco. Endpoints are loaded and called through the master module.
Also loads the config.
"""
import datetime
import orjson as json
import os
import time
import yaml

from multiprocessing import Process
from sanic import Sanic
from sanic.log import access_logger as logger
from sanic.response import text
from sanic_redis import SanicRedis
from comet import Manager, CometError

from . import Endpoint, SlackExporter, worker, __version__

app = Sanic(__name__)
app.config.update({"REDIS": {"address": ("127.0.0.1", 6379)}})
redis = SanicRedis(app)


@app.route("/<endpoint>", methods=["GET", "POST"])
async def master_endpoint(request, endpoint):
    """
    Receive all HTTP calls.

    Master endpoint. Passes all endpoint calls on to redis and blocks until completion.
    """
    # create a unique name for this task: <process ID>-<POSIX timestamp>
    name = f"{os.getpid()}-{time.time()}"
    logger.debug(f"name: {name}")

    with await redis.conn as r:

        # Give the task to redis
        await r.hmset(
            name,
            "method",
            request.method,
            "endpoint",
            endpoint,
            "request",
            json.dumps(request.json),
        )

        # Add task name to queue
        await r.rpush("queue", name)

        # Wait for the result
        logger.debug(f"Waiting for: {name}:res")
        result = (await r.blpop(f"{name}:res"))[1]
        await r.delete(f"{name}:res")
    return text(int(result))


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
        self.queue = Process(target=worker.main_loop, args=(self.endpoints,))
        self.queue.start()
        self._start_server()

    def __del__(self):
        """
        Destruct :class:`Master`.

        Join the worker thread.
        """
        self.queue.join()

    def _start_server(self):
        """Start a sanic server."""
        app.run(
            host="0.0.0.0", port=self.port, workers=self.n_workers, debug=True, access_log=True
        )

    # TODO: remove this? endpoints should only be called by worker process
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
        self.port = config["port"]
        self.n_workers = config["n_workers"]
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
