"""
coco master module.

This is the core of coco. Endpoints are loaded and called through the master module.
Also loads the config.
"""
import datetime
import logging
import orjson as json
import os
import redis as redis_sync
import time
import yaml
from tempfile import TemporaryDirectory

from multiprocessing import Process
from sanic import Sanic
from sanic.log import logger as logger
from sanic import response
from sanic.exceptions import ServerError
from sanic_redis import SanicRedis
from comet import Manager, CometError
from prometheus_client import multiprocess
from prometheus_client import generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST, Counter

from . import Endpoint, SlackExporter, worker, __version__, RequestForwarder, State
from .metric import format_metric_name

app = Sanic(__name__)
app.config.update({"REDIS": {"address": ("127.0.0.1", 6379)}})
redis = SanicRedis(app)
logger = logging.getLogger(__name__)

# global variables for prometheus metric tracking
_COUNTERS = dict()
_ENDPOINTS = []
_REGISTRY = None


@app.route("/<endpoint>", methods=["GET", "POST"])
async def master_endpoint(request, endpoint):
    """
    Receive all HTTP calls.

    Master endpoint. Passes all endpoint calls on to redis and blocks until completion.
    """
    # create a unique name for this task: <process ID>-<POSIX timestamp>
    name = f"{os.getpid()}-{time.time()}"

    # increment prometheus counter
    cnt = _COUNTERS.get(endpoint, None)
    if cnt is None:
        logger.error(f"No prometheus metric for endpoint {endpoint}.")
        exit(1)
    else:
        cnt.labels(worker=f"{os.getpid()}").inc()

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
        result = (await r.blpop(f"{name}:res"))[1]
        await r.delete(f"{name}:res")
    return response.raw(result, headers={"Content-Type": "application/json"})


# Prometheus endpoint
# This server can only export the total requests. Individual success/fail
# counts for every host will be exported separately by the forwarder process
@app.get("/metrics")
async def metrics(request):
    """
    Prometheus metrics endpoint.
    """
    try:
        output = generate_latest(_REGISTRY).decode("utf-8")
        content_type = CONTENT_TYPE_LATEST
        return response.text(body=output, content_type=content_type)
    except Exception as e:
        msg = f"{e}"
        logger.error(msg)
        raise ServerError(msg)


@app.listener('after_server_stop')
async def cleanup_prometheus(app, loop):
    """
    Clean up prometheus metric files on exit.
    """
    multiprocess.mark_process_dead(os.getpid())


@app.listener('before_server_start')
async def init_metrics(app, loop):
    """
    Set up counters for every endpoint.
    """
    global _COUNTERS
    for edpt in _ENDPOINTS:
        _COUNTERS[edpt] = Counter(format_metric_name(f"coco_{edpt}_dropped"),
                                  "Dropped requests due to full queue by coco.",
                                  ["worker"], unit="total", registry=_REGISTRY)
        _COUNTERS[edpt].labels(worker=os.getpid()).inc(0)


class Master:
    """
    The core module.

    Loads and keeps the config and endpoints. Endpoints are called through this module.
    """

    def __init__(self, config_path):

        # In case constructor crashes before this gets assigned, so that destructor doesn't fail.
        self.qworker = None

        self.forwarder = RequestForwarder()
        self.state = None
        config = self._load_config(config_path)
        logger.setLevel(self.log_level)
        self.forwarder.set_session_limit(self.session_limit)

        self.slacker = SlackExporter(self.slack_url)
        config["endpoints"] = self._load_endpoints()
        self._register_config(config)
        self._init_prometheus()
        self.qworker = Process(target=worker.main_loop, args=(self.endpoints, self.forwarder,
                                                              self.worker_port, self.log_level))
        self.qworker.start()

        self._call_endpoints_on_start()
        self._start_server()

    def __del__(self):
        """
        Destruct :class:`Master`.

        Join the worker thread.
        """
        if self.qworker:
            self.qworker.join()

    def _call_endpoints_on_start(self):
        for endpoint in self.endpoints.values():
            if endpoint.call_on_start:
                logger.debug(f"Calling endpoint on start: /{endpoint.name}")
                name = f"{os.getpid()}-{time.time()}"

                r = redis_sync.Redis()
                r.hmset(
                    name,
                    {
                        "method": endpoint.type,
                        "endpoint": endpoint.name,
                        "request": json.dumps({}),
                    },
                )

                # Add task name to queue
                r.rpush("queue", name)

                # Wait for the result
                result = r.blpop(f"{name}:res")[1]
                r.delete(f"{name}:res")
                # TODO: raise log level in failure case?
                logger.debug(f"Called /{endpoint.name} on start, result: {result}")

    def _start_server(self):
        """Start a sanic server."""
        debug = self.log_level == "DEBUG"
        app.run(
            host="0.0.0.0", port=self.port, workers=self.n_workers, debug=debug, access_log=debug
        )

    def _register_config(self, config):
        # Register config with comet broker
        try:
            enable_comet = config["comet_broker"]["enabled"]
        except KeyError:
            logger.error("Missing config value 'comet_broker/enabled'.")
            exit(1)
        if enable_comet:
            try:
                comet_host = config["comet_broker"]["host"]
                comet_port = config["comet_broker"]["port"]
            except KeyError as exc:
                logger.error(
                    "Failure registering initial config with comet broker: 'comet_broker/{}' "
                    "not defined in config.".format(exc[0])
                )
                exit(1)
            comet = Manager(comet_host, comet_port)
            try:
                comet.register_start(datetime.datetime.utcnow(), __version__)
                comet.register_config(config)
            except CometError as exc:
                logger.error(
                    "Comet failed registering CoCo startup and initial config: {}".format(exc)
                )
                exit(1)
        else:
            logger.warning("Config registration DISABLED. This is only OK for testing.")

    def _load_config(self, config_path):
        with open(config_path, "r") as stream:
            try:
                config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                logger.error(f"Failure reading YAML file {config_path}: {exc}")

        self.log_level = config.get("log_level", "INFO")
        self.endpoint_dir = config["endpoint_dir"]
        try:
            self.slack_url = config["slack_webhook"]
        except KeyError:
            self.slack_url = None
            logger.warning("Config variable 'slack_webhook' not found. Slack messaging DISABLED.")
        self.port = config["port"]
        self.worker_port = config["worker_port"]
        self.n_workers = config["n_workers"]
        self.session_limit = config.get("session_limit", 1000)

        # Read groups
        self.groups = config.get("groups", None)

        def format_host(host):
            if not host.startswith("http://"):
                host = "http://" + host
            if not host.endswith("/"):
                host = host + "/"
            return host

        for group in self.groups:
            for h in range(len(self.groups[group])):
                self.groups[group][h] = format_host(self.groups[group][h])

            self.forwarder.add_group(group, self.groups[group])

        # Load state from yaml config files
        self.state = State(log_level=self.log_level)
        load_state = config.get("load_state", None)
        if load_state:
            for path, file in load_state.items():
                self.state.read_from_file(path, file)

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
                        logger.error(f"Failure reading YAML file {endpoint_file}: {exc}")

                # Create the endpoint object
                self.endpoints[name] = Endpoint(
                    name, conf, self.slacker, self.forwarder, self.state
                )
                if self.endpoints[name].group not in self.groups:
                    if self.endpoints[name].forward_name is None:
                        logger.debug(
                            f"Endpoint {name} has `call` set to 'null'. This means it "
                            f"doesn't call external endpoints. It might check other coco "
                            f"endpoints or return some part of coco's state."
                        )
                    else:
                        raise RuntimeError(
                            f"Host group '{self.endpoints[name].group}' used by endpoint "
                            f"{name} unknown."
                        )
                conf["name"] = name
                endpoint_conf.append(conf)
                self.forwarder.add_endpoint(name, self.endpoints[name])

        self._check_endpoint_links()
        return endpoint_conf

    def _check_endpoint_links(self):
        def check(e):
            if e:
                for a in e:
                    if isinstance(a, dict):
                        if not len(a.keys()) is 1:
                            logger.error(
                                f"coco.endpoint: bad config format for endpoint "
                                f"`{endpoint.name}`: `{a}`. Should be either a string or "
                                f"have the format:\n```\nbefore:\n  - endpoint_name:\n   "
                                f"   identical: True\n```"
                            )
                            exit(1)
                        a = list(a.keys())[0]
                    if a not in self.endpoints.keys():
                        logger.error(
                            f"coco.endpoint: endpoint `{a}` found in config for "
                            f"`{endpoint.name}` does not exist."
                        )
                        exit(1)

        for endpoint in self.endpoints.values():
            check(endpoint.before)
            check(endpoint.after)

    def _init_prometheus(self):
        # Set directory for prometheus metrics to be stored
        self.prom_tmpdir = TemporaryDirectory()
        os.environ["prometheus_multiproc_dir"] = self.prom_tmpdir.name
        # Set global variables for prometheus
        global _ENDPOINTS
        _ENDPOINTS = self.endpoints.keys()
        global _REGISTRY
        _REGISTRY = CollectorRegistry()
        multiprocess.MultiProcessCollector(_REGISTRY)
