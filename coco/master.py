"""
coco master module.

This is the core of coco. Endpoints are loaded and called through the master module.
Also loads the config.
"""
import datetime
import logging
import time
import os
from pathlib import Path
from multiprocessing import Process

import orjson as json
import redis
import aioredis
import yaml

from sanic import Sanic, response

from comet import Manager, CometError

from . import (
    CocoForward,
    Endpoint,
    LocalEndpoint,
    worker,
    __version__,
    RequestForwarder,
    State,
    wait,
)
from .util import Host
from . import slack

logger = logging.getLogger(__name__)


class Master:
    """
    The core module.

    Loads and keeps the config and endpoints. Endpoints are called through this module.
    """

    def __init__(self, config_path):

        # In case constructor crashes before this gets assigned, so that destructor doesn't fail.
        self.qworker = None

        self.state = None

        # Load the config
        config = self._load_config(Path(config_path))
        logger.setLevel(self.log_level)

        # Configure the forwarder
        self.forwarder = RequestForwarder(self.blacklist_path)
        self.forwarder.set_session_limit(self.session_limit)
        for group, hosts in self.groups.items():
            self.forwarder.add_group(group, hosts)

        self._config_slack_loggers()

        config["endpoints"] = self._load_endpoints()
        self._local_endpoints()
        self._check_endpoint_links()
        self._register_config(config)

        # Remove any leftover shutdown commands from the queue
        self.redis_sync = redis.Redis()
        self.redis_sync.lrem("queue", 0, "coco_shutdown")

        # Load queue update script into redis cache
        self.queue_sha = self.redis_sync.script_load(
            """ if redis.call('llen', KEYS[1]) >= tonumber(ARGV[1]) then
                        return true
                    else
                        redis.call('hmset', KEYS[2], ARGV[2], ARGV[3], ARGV[4], ARGV[5], ARGV[6], ARGV[7], ARGV[8], ARGV[9])
                        redis.call('rpush', KEYS[1], KEYS[2])
                        return false
                    end
            """
        )

        # Start the worker process
        self.qworker = Process(
            target=worker.main_loop,
            args=(self.endpoints, self.forwarder, self.port, self.metrics_port, self.log_level),
        )
        self.qworker.daemon = True
        try:
            self.qworker.start()
        except BaseException:
            self.qworker.join()

        self._call_endpoints_on_start()
        self._start_server()

    def __del__(self):
        """
        Destruct :class:`Master`.

        Join the worker process.
        """
        logger.info("Joining worker process...")
        try:
            self.redis_sync.rpush("queue", "coco_shutdown")
        except BaseException as e:
            logger.error(
                f"Failed sending shutdown command to worker (have to kill it): {type(e)}: {e}"
            )
            self._kill_worker()
        self._kill_worker()

    def _kill_worker(self):
        if hasattr(self, "qworker"):
            if self.qworker:
                self.qworker.kill()

    def _call_endpoints_on_start(self):
        for endpoint in self.endpoints.values():
            # Initialise request counter
            self.redis_sync.incr(f"dropped_counter_{endpoint.name}", amount=0)
            if endpoint.call_on_start:
                logger.debug(f"Calling endpoint on start: /{endpoint.name}")
                name = f"{os.getpid()}-{time.time()}"

                self.redis_sync.hmset(
                    name,
                    {
                        "method": endpoint.type,
                        "endpoint": endpoint.name,
                        "request": json.dumps({}),
                    },
                )

                # Add task name to queue
                self.redis_sync.rpush("queue", name)

                # Wait for the result
                result = self.redis_sync.blpop(f"{name}:res")[1]
                self.redis_sync.delete(f"{name}:res")
                # TODO: raise log level in failure case?
                logger.debug(f"Called /{endpoint.name} on start, result: {result}")

    def _start_server(self):
        """Start a sanic server."""

        self.sanic_app = Sanic(__name__)

        # Create the Redis connection pool, use sanic to start it so that it
        # ends up in the same event loop
        async def init_redis_async(_, loop):
            self.redis_async = await aioredis.create_redis_pool(("127.0.0.1", 6379))

        async def close_redis_async(_, loop):
            self.redis_async.close()
            await self.redis_async.wait_closed()

        self.sanic_app.register_listener(init_redis_async, "before_server_start")
        self.sanic_app.register_listener(close_redis_async, "after_server_stop")

        # Set up slack logging, needs to be done here so it gets setup in the right event loop
        def start_slack_log(_, loop):
            slack.start(loop)

        def stop_slack_log(_, loop):
            slack.stop()

        self.sanic_app.register_listener(start_slack_log, "before_server_start")
        self.sanic_app.register_listener(stop_slack_log, "after_server_stop")

        debug = self.log_level == "DEBUG"

        self.sanic_app.add_route(self.external_endpoint, "/<endpoint>", methods=["GET", "POST"])

        self.sanic_app.run(
            host="0.0.0.0", port=self.port, workers=self.n_workers, debug=debug, access_log=debug
        )

    def _config_slack_loggers(self):
        # Configure the log handlers for posting to slack

        # Don't set up extra loggers if they're not enabled
        if self.slack_token is None:
            return

        # Set the authorization token
        slack.set_token(self.slack_token)

        for rule in self.slack_rules:

            logger_name = rule["logger"]
            channel = rule["channel"]
            level = rule.get("level", "INFO").upper()

            log = logging.getLogger(logger_name)

            handler = slack.SlackLogHandler(channel)
            handler.setLevel(level)
            log.addHandler(handler)

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

    def _load_config(self, config_path: os.PathLike):
        with config_path.open("r") as stream:
            try:
                config = yaml.safe_load(stream)
                if not config:
                    raise RuntimeError(f"Config file empty?")
            except yaml.YAMLError as exc:
                logger.error(f"Failure reading YAML file {config_path}: {exc}")

        self.log_level = config.get("log_level", "INFO")
        logger.setLevel(self.log_level)
        # Also set log level for root logger, inherited by all
        logging.getLogger().setLevel(self.log_level)
        self.endpoint_dir = config["endpoint_dir"]
        try:
            self.slack_token = config["slack_token"]
        except KeyError:
            self.slack_token = None
            logger.warning("Config variable 'slack_token' not found. Slack messaging DISABLED.")

        self.port = config.get("port", 12055)
        self.metrics_port = config.get("metrics_port", 9090)
        self.n_workers = config.get("n_workers", 1)
        self.session_limit = config.get("session_limit", 1000)

        # Read groups
        try:
            self.groups = config["groups"]
        except KeyError:
            logger.error(f"No groups found in {config_path}.")
            exit(1)

        # Get the blacklist path, if it's not absolute then it is resolved
        # relative to the config directory
        self.blacklist_path = Path(config.get("blacklist_path", "blacklist.json"))
        if not self.blacklist_path.is_absolute():
            self.blacklist_path = config_path.parent.joinpath(self.blacklist_path)

        # Read groups
        self.groups = config["groups"].copy() if "groups" in config else {}
        for group, hosts in self.groups.items():
            self.groups[group] = [Host(h) for h in hosts]

        # Load state from yaml config files
        self.state = State(log_level=self.log_level)
        load_state = config.get("load_state", None)
        if load_state:
            for path, file in load_state.items():
                self.state.read_from_file(path, file)

        # Load slack posting rules
        rules = config.get("slack_rules", [])
        self.slack_rules = []
        for rdict in rules:
            if "logger" not in rdict or "channel" not in rdict:
                logger.error(f"Invalid slack rule {rdict}.")
            self.slack_rules.append(rdict)

        # Set max queue length
        self.queue_length = config.get("queue_length", 0)

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
                self.endpoints[name] = Endpoint(name, conf, self.forwarder, self.state)

                if self.endpoints[name].group not in self.groups:
                    if not self.endpoints[name].has_external_forwards:
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

        return endpoint_conf

    def _local_endpoints(self):
        # Register any local endpoints

        endpoints = {
            "blacklist": ("GET", self.forwarder.blacklist.process_get),
            "update-blacklist": ("POST", self.forwarder.blacklist.process_post),
            "wait": ("POST", wait.process_post),
        }

        for name, (type_, callable) in endpoints.items():
            self.endpoints[name] = LocalEndpoint(name, type_, callable)
            self.forwarder.add_endpoint(name, self.endpoints[name])

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
                    if isinstance(a, CocoForward):
                        a = a.name
                    if a not in self.endpoints.keys():
                        logger.error(
                            f"coco.endpoint: endpoint `{a}` found in config for "
                            f"`{endpoint.name}` does not exist."
                        )
                        exit(1)

        for endpoint in self.endpoints.values():
            if hasattr(endpoint, "before"):
                check(endpoint.before)
            if hasattr(endpoint, "after"):
                check(endpoint.after)
            if hasattr(endpoint, "forward_to_coco"):
                check(endpoint.forward_to_coco)

    async def external_endpoint(self, request, endpoint):
        """
        Receive all HTTP calls.

        Master endpoint. Passes all endpoint calls on to redis and blocks until completion.
        """
        # create a unique name for this task: <process ID>-<POSIX timestamp>
        name = f"{os.getpid()}-{time.time()}"

        with await self.redis_async as r:
            # Check if queue is full. If not, add this task.
            if self.queue_length > 0:
                full = await r.evalsha(
                    self.queue_sha,
                    keys=["queue", name],
                    args=[
                        self.queue_length,
                        "method",
                        request.method,
                        "endpoint",
                        endpoint,
                        "request",
                        request.body,
                        "params",
                        request.query_string,
                    ],
                )

                if full:
                    # Increment dropped request counter
                    await r.incr(f"dropped_counter_{endpoint}")
                    return response.json(
                        {"reply": "Coco queue is full.", "status": 503}, status=503
                    )
            else:
                # No limit on queue, just give the task to redis
                await r.hmset(
                    name,
                    "method",
                    request.method,
                    "endpoint",
                    endpoint,
                    "request",
                    request.body,
                    "params",
                    request.query_string,
                )

                # Add task name to queue
                await r.rpush("queue", name)

            # Wait for the result (operations must be in this order to ensure
            # the result is available)
            code = int((await r.blpop(f"{name}:code"))[1])
            result = (await r.blpop(f"{name}:res"))[1]
            await r.delete(f"{name}:res")
            await r.delete(f"{name}:code")

        return response.raw(result, status=code, headers={"Content-Type": "application/json"})
