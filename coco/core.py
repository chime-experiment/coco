"""
coco core module.

This is the core of coco. Endpoints are loaded and called through the core module.
Also loads the config.  It also contains the CLI entry-point of the coco server.
"""

import asyncio
import datetime
import json
import logging
import os
import socket
import time
from multiprocessing import Process, set_start_method
from pathlib import Path

import click
import redis
from comet import CometError, Manager
from redis import asyncio as aioredis
from sanic import Sanic, response

from . import config, slack, wait, worker
from .endpoint import (
    Endpoint,
    LocalEndpoint,
)
from .exceptions import InternalError
from .request_forwarder import (
    CocoForward,
    RequestForwarder,
)
from .result import Result
from .state import State
from .util import Host, PersistentState, str2total_seconds

Sanic.START_METHOD_SET = True
Sanic.start_method = "fork"

logger = logging.getLogger(__name__)

# This should be a no-op on Linux but is required on MacOS for coco to run
try:
    set_start_method("fork", force=True)
except RuntimeError:
    pass


class Core:
    """
    The core module.

    Loads and keeps the config and endpoints. Endpoints are called through this module.
    """

    def __init__(
        self, conf, full_reset=False, reset=False, check_config=False, testing=False
    ):
        """
        Coco Core.

        Parameters
        ----------
        conf : os.PathLike or None
            Path to the config file, if any.
        full_reset : bool
            Fully-reset the state, including parts normally excluded from
            reset.  Default `False`.
        reset : bool
            Whether to reset internal state on start. Default `False`.
        check_config : bool
            Don't really start, check config only. Default `False`.
        testing : bool
            Run in testing mode.  This binds the coco daemon to a random port
            instead of the one specified in the config.  It also skips loading
            any config from the standard config file paths.  (Config files
            specified by COCO_CONFIG_FILE or on the command line are still loaded.)
        """

        # full_reset overrides reset
        if full_reset:
            reset = False

        # In case constructor crashes before this gets assigned, so that destructor
        # doesn't fail.
        self.qworker = None
        self.state = None
        self.redis_sync = None

        # Load the config
        self._load_config(conf, testing)

        # Init state, tries loading from persistent storage, or fully-reset it
        self.state = State(
            Path(self.config["storage_path"]),
            self.config["load_state"],
            self.config["exclude_from_reset"],
            reset_on_init=full_reset,
        )

        # Normal reset
        if reset:
            asyncio.run(self.state.reset_state())

        # Configure the forwarder
        try:
            timeout = str2total_seconds(self.config["timeout"])
        except ValueError as e:
            raise click.ClickException(
                f"Failed parsing value 'timeout' ({self.config['timeout']}): {e}"
            ) from e
        self.forwarder = RequestForwarder(
            self.blocklist_path,
            timeout,
            debug_connections=self.config["debug_connections"],
        )
        self.forwarder.set_session_limit(self.config["session_limit"])
        for group, hosts in self.groups.items():
            self.forwarder.add_group(group, hosts)

        self._config_slack_loggers()

        self._load_endpoints()
        self._local_endpoints()
        self._check_endpoint_links()
        self._register_config()

        try:
            self.frontend_timeout = str2total_seconds(self.config["frontend_timeout"])
        except ValueError as e:
            raise click.ClickException(
                "Failed parsing value 'frontend_timeout' "
                f"({self.config['frontend_timeout']}): {e}"
            ) from e

        if check_config:
            logger.info("Superficial config check successful. Stopping...")
            return

        # Remove any leftover shutdown commands from the queue
        self.redis_sync = redis.Redis(port=int(self.config["redis_port"]))
        self.redis_sync.lrem("queue", 0, "coco_shutdown")

        # Load queue update script into redis cache
        self.queue_sha = self.redis_sync.script_load(
            """ if redis.call('llen', KEYS[1]) >= tonumber(ARGV[1]) then
                        return true
                    else
                        redis.call('hmset', KEYS[2], ARGV[2], ARGV[3], ARGV[4], ARGV[5], ARGV[6], ARGV[7], ARGV[8], ARGV[9], ARGV[10], ARGV[11])
                        redis.call('rpush', KEYS[1], KEYS[2])
                        return false
                    end
            """  # noqa: E501
        )

        if testing:
            # Create TCP/IP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # bind to an ephemeral port on localhost
            sock.bind(("127.0.0.1", 0))

            # Store the bound port back in the config so cocod knows how
            # to talk to itself
            self.config["port"] = sock.getsockname()[1]
        else:
            sock = None

        # Start the worker process
        self.qworker = Process(
            target=worker.main_loop,
            args=(
                self.endpoints,
                self.forwarder,
                self.config["port"],
                self.config["metrics_port"],
                self.frontend_timeout,
            ),
        )
        self.qworker.daemon = True
        try:
            self.qworker.start()
        except RuntimeError:
            self.qworker.join()

        self._call_endpoints_on_start()

        # This blocks until cocod terminates
        self._start_server(sock)

        self.redis_async = None

    def __del__(self):
        """
        Destruct :class:`Core`.

        Join the worker process.
        """
        if self.redis_sync:
            logger.info("Joining worker process...")
            try:
                self.redis_sync.rpush("queue", "coco_shutdown")
            except RuntimeError as e:
                logger.error(
                    "Failed sending shutdown command to worker "
                    f"(have to kill it): {type(e)}: {e}"
                )
            self._kill_worker()

    def _kill_worker(self):
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

    def _start_server(self, sock: socket.socket | None = None):
        """Start a sanic server.

        Parameters
        ----------
        sock : socket.socket or None
            A bound socket for Sanic to listen on, if in --testing mode,
            or None, in production mode.
        """
        self.sanic_app = Sanic("coco_core")
        self.sanic_app.config.REQUEST_TIMEOUT = self.frontend_timeout
        self.sanic_app.config.RESPONSE_TIMEOUT = self.frontend_timeout

        # Create the Redis connection pool, use sanic to start it so that it
        # ends up in the same event loop
        async def init_redis_async(*_):
            self.redis_async = aioredis.Redis(
                host="localhost",
                port=int(self.config["redis_port"]),
                encoding="utf-8",
                decode_responses=True,
            )
            await self.redis_async.ping()

        self.sanic_app.register_listener(init_redis_async, "before_server_start")

        # Set up slack logging, needs to be done here so it gets setup in the
        # right event loop
        def start_slack_log(_, loop):
            slack.start(loop)

        async def stop_slack_log(*_):
            await slack.stop()

        self.sanic_app.register_listener(start_slack_log, "before_server_start")
        self.sanic_app.register_listener(stop_slack_log, "after_server_stop")

        self.sanic_app.add_route(
            self.external_endpoint, "/<endpoint>", methods=["GET", "POST"]
        )

        # If we already have a bound socket, pass that to sanic (we're in
        # --testing mode)
        if sock:
            # Pass the bound socket to sanic
            sanic_opts = {"sock": sock}

            # Write talkback to signal runner that we're ready to start-up
            PersistentState(
                Path(self.config["storage_path"], "_TESTING"),
                set_to={"port": self.config["port"]},
            )
        else:
            # Regular (non-testing) mode: get sanic to bind the port itself
            sanic_opts = {
                "host": "0.0.0.0",
                "port": self.config["port"],
                "debug": (self.log_level == "DEBUG"),
            }

        self.sanic_app.run(
            **sanic_opts,
            workers=self.config["n_workers"],
            access_log=sanic_opts["debug"],
        )

    def _config_slack_loggers(self):
        # Configure the log handlers for posting to slack

        # Don't set up extra loggers if they're not enabled
        if self.config["slack_token"] is None:
            logger.warning(
                "Config variable 'slack_token' not found. Slack messaging DISABLED."
            )
            return

        # Set the authorization token
        slack.set_token(self.config["slack_token"])

        for rule in self.config["slack_rules"]:
            logger_name = rule["logger"]
            channel = rule["channel"]
            level = rule.get("level", "INFO").upper()

            log = logging.getLogger(logger_name)

            handler = slack.SlackLogHandler(channel)
            handler.setLevel(level)
            log.addHandler(handler)

    def _register_config(self):
        # Register config with comet broker
        from . import __version__

        try:
            enable_comet = self.config["comet_broker"]["enabled"]
        except KeyError as e:
            raise click.ClickException(
                "Missing config value 'comet_broker/enabled'."
            ) from e
        if enable_comet:
            try:
                comet_host = self.config["comet_broker"]["host"]
                comet_port = self.config["comet_broker"]["port"]
            except KeyError as exc:
                raise InternalError(
                    "Failure registering initial config with comet broker: "
                    f"'comet_broker/{exc}' not defined in config."
                ) from exc
            comet = Manager(comet_host, comet_port)

            try:
                comet.register_start(
                    datetime.datetime.now(datetime.timezone.utc),
                    __version__,
                    self.config,
                )
            except CometError as exc:
                raise InternalError(
                    f"Comet failed registering CoCo startup and initial config: {exc}"
                ) from exc
        else:
            logger.warning("Config registration DISABLED. This is only OK for testing.")

    def _load_config(self, config_path: os.PathLike | None, testing: bool):
        self.config = config.load_config(config_path, testing=testing)

        # Set log level, if valid
        self.log_level = self.config["log_level"]

        try:
            logging.getLogger("coco").setLevel(self.log_level)
            # Also set log level for root logger, inherited by all
            logging.getLogger().setLevel(self.log_level)
        except ValueError as e:
            raise click.ClickException(f"Unable to set log level: {e}") from e

        # Get the state storage and blocklist path, if it's not absolute then
        # it is resolved relative to the config directory
        self.blocklist_path = Path(self.config["blocklist_path"])
        if not self.blocklist_path.is_absolute():
            raise click.ClickException(
                f'Blocklist path "{self.config["blocklist_path"]}" must be absolute.'
            )
        storage_path = Path(self.config["storage_path"])
        if not storage_path.is_absolute():
            raise click.ClickException(
                f'Storage path "{self.config["storage_path"]}" must be absolute.'
            )
        if not storage_path.is_dir():
            raise click.ClickException(
                f'Storage path "{self.config["storage_path"]}" is not a directory.'
            )

        # Parse groups
        self.groups = {}
        try:
            for group, hosts in self.config["groups"].items():
                if not isinstance(hosts, list):
                    raise TypeError()
                self.groups[group] = [Host(h) for h in hosts]
        except (TypeError, AttributeError) as e:
            raise click.ClickException(
                "groups must be a map containing host lists."
            ) from e
        except ValueError as e:
            raise click.ClickException(f"bad hostname in groups: {e}") from e

        # Validate slack posting rules
        for rdict in self.config["slack_rules"]:
            for key in ["logger", "channel"]:
                if key not in rdict:
                    raise click.ClickException(
                        f"Required key {key} missing from slack rule: {rdict}."
                    )

    def _load_endpoints(self):
        self.endpoints = {}

        for conf in self.config["endpoints"]:
            name = conf["name"]

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
            self.forwarder.add_endpoint(name, self.endpoints[name])

    def _local_endpoints(self):
        # Register any local endpoints

        endpoints = {
            "blocklist": ("GET", self.forwarder.blocklist.process_get),
            "update-blocklist": ("POST", self.forwarder.blocklist.process_post),
            "saved-states": ("GET", self.state.get_saved_states),
            "reset-state": ("POST", self.state.reset_state),
            "save-state": ("POST", self.state.save_state),
            "load-state": ("POST", self.state.load_state),
            "get-coco-config": ("GET", self._get_config),
            "wait": ("POST", wait.process_post),
        }

        for name, (type_, callable_) in endpoints.items():
            self.endpoints[name] = LocalEndpoint(name, type_, callable_)
            self.forwarder.add_endpoint(name, self.endpoints[name])

    async def _get_config(self, _):
        return Result(
            "coco-config",
            result={Host("coco"): (self.config, 200)},
            type_="FULL",
        )

    def _check_endpoint_links(self):
        def check(e):
            if e:
                for a in e:
                    if isinstance(a, dict):
                        keys = list(a.keys())
                        if len(keys) != 1:
                            raise click.ClickException(
                                f"coco.endpoint: bad config format for endpoint "
                                f"`{e.name}`: `{a}`. Should be either a string or "
                                "have the format:\n"
                                "```\n"
                                "before:\n"
                                "  - endpoint_name:\n"
                                "      identical: True\n"
                                "```"
                            )
                        a = keys[0]
                    if isinstance(a, CocoForward):
                        a = a.name
                    if a not in self.endpoints:
                        raise click.ClickException(
                            f"coco.endpoint: endpoint `{a}` found in config for "
                            f"`{e.name}` does not exist."
                        )

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

        Core endpoint. Passes all endpoint calls on to redis and blocks until
        completion.
        """
        # create a unique name for this task: <process ID>-<POSIX timestamp>
        now = time.perf_counter()
        name = f"{os.getpid()}-{now}"

        async with self.redis_async.client() as ra_cli:
            # Check if queue is full. If not, add this task.
            if self.config["queue_length"] > 0:
                full = await ra_cli.evalsha(
                    self.queue_sha,
                    2,
                    "queue",
                    name,
                    self.config["queue_length"],
                    "method",
                    request.method,
                    "endpoint",
                    endpoint,
                    "request",
                    request.body,
                    "params",
                    request.query_string,
                    "received",
                    now,
                )

                if full:
                    # Increment dropped request counter
                    await ra_cli.incr(f"dropped_counter_{endpoint}")
                    return response.json(
                        {"reply": "Coco queue is full.", "status": 503}, status=503
                    )
            else:
                # No limit on queue, just give the task to redis
                await ra_cli.hmset(
                    name,
                    {
                        "method": request.method,
                        "endpoint": endpoint,
                        "request": request.body,
                        "params": request.query_string,
                        "received": now,
                    },
                )

                # Add task name to queue
                await ra_cli.rpush("queue", name)

            # Wait for the result (operations must be in this order to ensure
            # the result is available)
            code = int((await ra_cli.blpop(f"{name}:code"))[1])
            result = (await ra_cli.blpop(f"{name}:res"))[1]
            await ra_cli.delete(f"{name}:res")
            await ra_cli.delete(f"{name}:code")

        return response.raw(
            result, status=code, headers={"Content-Type": "application/json"}
        )


@click.command()
@click.option("--check-config", is_flag=True, default=False, help="Check config only")
@click.option(
    "-c",
    "--conf",
    metavar="PATH",
    help="Read coco conf file specified by PATH",
)
@click.option(
    "--full-reset",
    is_flag=True,
    default=False,
    help="Fully reset the internal state on start.  Similar to --reset except this "
    "also resets everything that is normally excluded from reset.  Use this if "
    "active state on disk is corrupt and coco can't start-up.",
)
@click.option(
    "--reset", is_flag=True, default=False, help="Reset the internal state on start"
)
@click.option(
    "--testing",
    is_flag=True,
    default=False,
    help="Enable testing.  This should only be used when running cocod inside the "
    "the coco test suite.  See the coco_runner fixture for detauls.",
)
def cocod(conf, full_reset, reset, check_config, testing):
    """This is the coco (Config Control) server."""
    Core(
        conf=conf,
        full_reset=full_reset,
        reset=reset,
        check_config=check_config,
        testing=testing,
    )
    return 0
