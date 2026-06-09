"""coco endpoint module."""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from copy import copy

import click
import sanic
from aiohttp import (
    ClientSession,
    ContentTypeError,
)

from . import metric
from .check import (
    Check,
    IdenticalReplyCheck,
    StateHashReplyCheck,
    StateReplyCheck,
    TypeReplyCheck,
    ValueReplyCheck,
)
from .exceptions import InvalidUsage
from .request_forwarder import CocoForward, ExternalForward
from .result import Result
from .util import str2total_seconds

# Module level logger, note that there is also a class level, endpoint specific logger
logger = logging.getLogger(__name__)

# Supported types for endpoint values
VALUE_TYPE = {
    "bool": bool,
    "dict": dict,
    "float": float,
    "int": int,
    "list": list,
    "str": str,
}


class Endpoint:
    """
    An endpoint.

    Does whatever the config says.
    """

    def __init__(self, name, conf, forwarder, state):
        logger.debug(f"Loading {name}.conf")
        self.name = name
        if conf is None:
            conf = {}
        self.description = conf["description"]
        self.type = conf["type"]
        self.group = conf.get("group", None)
        self.callable = conf["callable"]
        self.report_latency = conf["report_latency"]
        self.call_on_start = conf["call_on_start"]
        self.forwarder = forwarder
        self.state = state
        self.report_type = conf["report_type"]
        self.values = copy(conf.get("values", None))
        self.get_state = conf.get("get_state", None)
        self.send_state = conf.get("send_state", None)
        self.save_state = conf.get("save_state", None)
        self.set_state = conf.get("set_state", None)
        self.schedule = conf.get("schedule", None)
        self.enforce_group = conf["enforce_group"]
        self.forward_checks = {}

        # Setup the endpoint logger
        self.logger = logging.getLogger(f"{__name__}.{self.name}")

        if self.values:
            for key, value in self.values.items():
                self.values[key] = VALUE_TYPE[value]

        if not self.state:
            return

        # To hold forward calls: first external ones than internal (coco) endpoints.
        self.has_external_forwards = False
        self._load_calls(conf.get("call", None))

        self.before = []
        self.after = []
        self._load_internal_forward(conf.get("before"), self.before)
        self._load_internal_forward(conf.get("after"), self.after)

    def _load_internal_forward(self, dict_, list_):
        """
        Load Forwards from the config dictionary, generate objects and place in list.

        Parameters
        ----------
        dict_ : dict, str, list[dict] or list[str]
            Config dict(s) describing an internal forward or just string(s) with
            endpoint name.
        list_ : list[CocoForward]
            The list to save the Forward objects in.
        """
        if not dict_:
            return
        if not isinstance(dict_, list):
            dict_ = [dict_]

        for f in dict_:
            if isinstance(f, dict):
                name = f["name"]
                try:
                    request = f.pop("request")
                except KeyError:
                    request = None

                list_.append(
                    CocoForward(
                        name, self.forwarder, None, request, self._load_checks(f)
                    )
                )
            else:
                list_.append(CocoForward(f, self.forwarder, None, None, None))

    def _load_calls(self, call_dict):
        """Parse the dict from forwarding config and save the Forward objects."""
        self.forwards_external = []
        self.forwards_internal = []
        if call_dict is None:
            # If no calls are specified an implicit external forward to an endpoint of
            # the same name is assumed.
            self.forwards_external.append(
                ExternalForward(self.name, self.forwarder, self.group, None, None)
            )
            self.has_external_forwards = True
            return

        # External forwards
        forward_ext = call_dict.get("forward", [self.name])
        if forward_ext:
            for f in forward_ext:
                if isinstance(f, str):
                    self.forwards_external.append(
                        ExternalForward(f, self.forwarder, self.group, None, None)
                    )
                # could also be a block where there are checks configured
                # for each forward call
                elif isinstance(f, dict):
                    timeout = f.get("timeout", None)
                    if timeout is not None:
                        timeout = str2total_seconds(timeout)

                    self.forwards_external.append(
                        ExternalForward(
                            f["name"],
                            self.forwarder,
                            self.group,
                            None,
                            self._load_checks(f),
                            timeout,
                        )
                    )
                self.has_external_forwards = True

        # Internal forwards
        forward_to_coco = call_dict.get("coco", None)
        self._load_internal_forward(forward_to_coco, self.forwards_internal)

    def _load_checks(self, check_dict: dict) -> list[Check]:
        if not check_dict:
            return []
        checks = []
        name = check_dict["name"]

        reply = check_dict.get("reply", None)
        if reply:
            on_failure = check_dict.get("on_failure", None)
            save_to_state = check_dict.get("save_reply_to_state", None)
            values = reply.get("value", None)
            types = reply.get("type", None)
            identical = reply.get("identical", None)
            state = reply.get("state", None)
            state_hash = reply.get("state_hash", None)
            num_hosts_warning = check_dict.get("num_hosts_warning", None)
            if values:
                checks.append(
                    ValueReplyCheck(
                        name,
                        values,
                        on_failure,
                        save_to_state,
                        self.forwarder,
                        self.state,
                        num_hosts_warning,
                    )
                )
            if types:
                checks.append(
                    TypeReplyCheck(
                        name,
                        types,
                        on_failure,
                        save_to_state,
                        self.forwarder,
                        self.state,
                        num_hosts_warning,
                    )
                )
            if identical:
                checks.append(
                    IdenticalReplyCheck(
                        name,
                        identical,
                        on_failure,
                        save_to_state,
                        self.forwarder,
                        self.state,
                        num_hosts_warning,
                    )
                )
            if state:
                checks.append(
                    StateReplyCheck(
                        name,
                        state,
                        on_failure,
                        save_to_state,
                        self.forwarder,
                        self.state,
                        num_hosts_warning,
                    )
                )
            if state_hash:
                checks.append(
                    StateHashReplyCheck(
                        name,
                        state_hash,
                        on_failure,
                        save_to_state,
                        self.forwarder,
                        self.state,
                        num_hosts_warning,
                    )
                )

        return checks

    async def call(self, request, hosts=None, params=None):
        """
        Call the endpoint.

        Returns
        -------
        :class:`Result`
            The result of the endpoint call.
        """
        self.logger.debug("endpoint called")

        if params is None:
            params = []

        if self.enforce_group:
            hosts = None

        result = Result(self.name)

        if self.before:
            for forward in self.before:
                result_forward = await forward.trigger(self.type, {}, hosts)
                result.embed(forward.name, result_forward)
                # TODO: run these concurrently?

        # Only forward values we expect
        filtered_request = copy(self.values)
        if request is None:
            request = {}
        if filtered_request:
            for key, value in filtered_request.items():
                try:
                    if not isinstance(request[key], value):
                        msg = (
                            f"{self.name} received value '{key}'' of type "
                            f"{type(request[key]).__name__} "
                            f"(expected {value.__name__})."
                        )
                        self.logger.warning(msg)
                        raise InvalidUsage(msg)
                except KeyError as e:
                    msg = f"{self.name} requires value '{key}'."
                    self.logger.warning(msg)
                    raise InvalidUsage(msg) from e

                # save the state change:
                if self.save_state:
                    for path in self.save_state:
                        self.state.write(path, request.get(key), key)

                filtered_request[key] = request.pop(key)

        # log the request content
        msg = ""
        if filtered_request:
            for k, v in filtered_request.items():
                msg = f"{msg}{k}: {v}\n"
            msg = msg[:-1]
        self.logger.info(msg)

        # Send values from state if not found in request (some type checking is
        # done at start-up and when state changed)
        if self.send_state:
            send_state = self.state.read(self.send_state)
            if filtered_request:
                send_state.update(filtered_request)
            filtered_request = send_state

        # Forward the request to group and then to other coco endpoints
        # TODO: should we do that concurrently?
        for forward in self.forwards_external:
            result_forward = await forward.trigger(
                self.type, filtered_request, hosts, params
            )
            result.add_result(result_forward)
        for forward in self.forwards_internal:
            result_forward = await forward.trigger(
                self.type, filtered_request, hosts, params
            )
            result.embed(forward.name, result_forward)

        # Look for result type parameter in request
        if request:
            result.type = request.pop("coco_report_type", self.report_type)
        else:
            result.type = self.report_type

        # Report any additional values in the request
        if request:
            for key in request.keys():
                msg = f"Found additional value '{key}' in request to /{self.name}."
                self.logger.warning(msg)
                result.add_message(msg)

        if self.after:
            for forward in self.after:
                result_forward = await forward.trigger(self.type, {}, hosts)
                result.embed(forward.name, result_forward)
                # TODO: run these concurrently?

        if self.get_state:
            result.state(self.state.extract(self.get_state))

        if result.success:
            if self.set_state:
                for path, value in self.set_state.items():
                    self.state.write(path, value)
            self.write_timestamp()
            self.logger.debug("Success!")

        result.report_latency = self.report_latency

        return result

    def write_timestamp(self):
        """
        Write a Unix timestamp (float) to the state.

        Does nothing if the endpoint doesn't have a path specified in `timestamp`.
        """
        if not self.timestamp_path:
            return
        self.state.write(self.timestamp_path, time.time())
        self.logger.debug(
            f"/{self.name} saved timestamp to state: {self.timestamp_path}"
        )

    def client_call(self, host, port, metrics_port, args):
        """
        Call from a client.

        Send a request to coco daemon at <host>. Return the reply as json or an
        error string.

        Parameters
        ----------
        host : str
            Address of coco daemon.
        port : int
            Port of coco daemon.
        metrics_port : int
            Port of the prometheus server
        args : :class:`Namespace`
            Is expected to include all values of the endpoint.
        """
        data = copy(self.values)
        if data:
            for key, type_ in data.items():
                data[key] = self._parse_container_arg(key, type_, vars(args)[key])
        else:
            data = {}
        args.endpoint = self.name
        args.type = self.type
        args.data = data
        return self.client_send_request(host, port, metrics_port, args)

    @staticmethod
    def client_send_request(host, port, metrics_port, args):
        """
        Send a request to an endpoint.

        Parameters
        ----------
        host : str
            Host.
        port : int
            Port.
        metrics_port : int
            Port of the prometheus server
        endpoint : str
            Endpoint name.
        type : str
            HTTP request type.
        data : json
            JSON data.
        args : :class:`argparse.Namespace`
            Namespace populated by argparse. May contain the report type
            (`report : str`), the refresh time for the client  in seconds
            ('client-refresh-time' : int) and ('silent' : boolean) to suppress printing
            anything but the result.

        Returns
        -------
        bool
            Success
        json or str
            The reply
        """
        data = args.data
        endpoint = args.endpoint
        type_ = args.type
        data["coco_report_type"] = args.report

        async def print_queue_size(metric_request_count):
            try:
                q_size = await metric.get("coco_queue_length_total", metrics_port, host)
            except RuntimeError as err:
                if not isinstance(err, asyncio.CancelledError):
                    print(f"Couldn't get queue fill level from cocod: {err}")
                return
            print(
                f"\rThere are {int(q_size)} requests in the queue.",
                sep=" ",
                end="",
                flush=True,
            )
            if metric_request_count % 2:
                print(" ", sep=" ", end="", flush=True)
            else:
                print(".", sep=" ", end="", flush=True)

        async def send_request():
            url = f"http://{host}:{port}/{endpoint}"
            if not args.silent:
                print("Sending request...")

            async with ClientSession() as session:
                try:
                    command = getattr(session, type_.lower())
                    async with command(url, json=data) as resp:
                        try:
                            result = await resp.json()
                        except ContentTypeError:
                            result = {"Error": await resp.text()}
                except RuntimeError as e:
                    return False, f"coco-client: Sending request failed: {e}"
                else:
                    return True, result

        async def request_and_wait():
            """
            Send the request and while waiting get and print queue fill level metric.

            Returns
            -------
                Done task for request result.
            """
            main_request = asyncio.create_task(send_request())
            if not args.silent:
                metric_request_count = 0
                while True:
                    metric_request_count = metric_request_count + 1
                    queue_size = asyncio.create_task(
                        print_queue_size(metric_request_count)
                    )
                    # Wait until either main request or request for metric is done
                    done, _ = await asyncio.wait(
                        {main_request, queue_size}, return_when=asyncio.FIRST_COMPLETED
                    )
                    if main_request in done:
                        queue_size.cancel()
                        print("\n")
                        break

                    # Wait a moment before getting metric again
                    wait = asyncio.create_task(asyncio.sleep(args.client_refresh_time))
                    # Cancel waiting in case main request is done
                    done, _ = await asyncio.wait(
                        {main_request, wait}, return_when=asyncio.FIRST_COMPLETED
                    )
                    if main_request in done:
                        wait.cancel()
                        print("\n")
                        break
            return await main_request

        return asyncio.run(request_and_wait())

    @staticmethod
    def _parse_container_arg(key, type_, arg):
        if type_ in (list, dict):
            try:
                value = json.loads(arg)
            except json.JSONDecodeError as e:
                raise InvalidUsage(f"Failure parsing argument '{key}': {e}") from e
            return value
        return arg


class LocalEndpoint:
    """An endpoint that will execute a callable solely within coco.

    Parameters
    ----------
    name
        Endpoint name.
    type_
        Type of request to accept. Either a string ("POST", ...) or a list of
        strings.
    callable
        A callable that will be called to execute the endpoint.
    """

    call_on_start = False

    def __init__(
        self,
        name: str,
        type_: str | list[str],
        callable: Callable[[sanic.request.Request], dict | None],
    ):
        self.name = name
        self.type = type_
        self.callable = callable
        self.report_latency = False
        self.schedule = None

    async def call(self, request, **_):
        """Call the local endpoint."""
        return await self.callable(request)


def _validate_enum(
    parameter: str, value: str, options: list[str], location: str | None = None
) -> str:
    """Validate an enum in the endpoint config.

    Parameters
    ----------
    parameter:
        Name of the parameter being validated
    value:
        Value of the parameter, if any
    options:
        Allowed values
    location:
        Location of the parameter.  If None, assumed to be part
        of "parameter".

    Returns
    -------
    str
        `value`.
    """

    if location:
        parameter += f" in {location}"

    if value not in options:
        raise click.ClickException(f"unknown {parameter}.  Expected one of {options}")
    return value


def _validate_dict(conf: dict, name: str, keys: tuple, location: str) -> None:
    """Validate a dict in the endpoint config.

    Parameters
    ----------
    conf:
        The config to validate.
    name:
        The name of the parameter being validated
    keys:
        Allowed keys in conf
    location:
        Location description for error strings.
    """
    if not isinstance(conf, dict):
        raise click.ClickException(f"expected mapping for {name!r} in {location}")

    for key in conf:
        _validate_enum(f"parameter {key!r} in {name!r} in {location}", key, keys)


def _validate_forwards(endpoint: str, forwards: dict | str | list, desc: str) -> list:
    """Validate a list of endpoint forwards.

    Returns the fixed-up list of forwards.

    Parameters
    ----------
    endpoint : str
        Endpoint name
    forwards:
        The config section to check and fix-up.  This should be a string or a dict
        or a list of strings and/or dicts.
    desc : str
        A description of which forwards are being validated, used
        in error strings.
    """

    # Handle explicitly disabled forwards
    if forwards is None:
        return None

    # Otherwise, listify
    if not isinstance(forwards, list):
        forwards = [forwards]

    for forward in forwards:
        # Set the location used in error strings.
        location = desc + " of " + endpoint

        # If the forward is a string, we're done checking it
        # (it's just an endpoint name).
        if isinstance(forward, str):
            continue

        # Otherwise, it must be a dict
        if not isinstance(forward, dict):
            raise click.ClickException(f"expected mapping or string for {location}.")

        # It must have a name
        if "name" not in forward:
            raise click.ClickException(f"name missing from {location}.")

        # now we can add the name to the location
        location = f"{desc} {forward['name']!r} of {endpoint}"

        # save_reply_to_state must be a string or dict
        if "save_reply_to_state" in forward:
            if not isinstance(forward["save_reply_to_state"], (str, dict)):
                raise click.ClickException(
                    f"save_reply_to_state in {location} must be a string or mapping"
                )

        # check on_failure
        if "on_failure" in forward:
            _validate_dict(
                forward["on_failure"],
                "on_failure",
                ("call", "call_single_host"),
                location,
            )

            for key in forward["on_failure"]:
                if not isinstance(forward["on_failure"][key], (str, int, float)):
                    raise click.ClickException(
                        f"on_failure value for {key!r} in {location} must be a string"
                    )
                forward["on_failure"][key] = str(forward["on_failure"][key])

        # check reply
        if "reply" in forward:
            reply = forward["reply"]
            _validate_dict(
                reply,
                "reply",
                (
                    "identical",
                    "num_hosts_warning",
                    "state",
                    "state_hash",
                    "type",
                    "value",
                ),
                location,
            )

            if not reply:
                logger.warning(f"'reply' in {location} is empty and will be ignored.")
                del forward["reply"]

    return forwards


def _validate_state_values(path, state, values, param, endpoint):
    """Validate a state path in an endpoint with values.

    Parameters
    ----------
    path:
        State path to check
    state:
        The loaded, active state
    values:
        The "values" part of the endpoint config
    param:
        The parameter being checked.  One of "get", "save", "send", "set".
    endpoint:
        Name of the endpoint being validated
    """
    location = f"'/{path}' referenced by '{param}_state' of {endpoint}"
    state_path = state.find_or_create(path)

    if not state_path:
        if param == "save":
            severity = logger.debug
        else:
            severity = logger.warn
        severity(f"{location} is empty.")
        return

    for value, type_ in values.items():
        if value in state_path:
            if state_path[value]:
                if not isinstance(state_path[value], VALUE_TYPE[type_]):
                    raise click.ClickException(
                        f"Value {value!r} in state at {location} has type "
                        f"{type(state_path[value]).__name__} "
                        f"(expected {type_})."
                    )

                # For send_state, if a endpoint value is also in the
                # state being sent, the version in the state won't be used
                # because it's overwritten by the caller-supplied value
                if param == "send":
                    logger.debug(
                        f"Value {value} in state at {location} will be ignored "
                        "because it is overwritten by the endpoint's 'values'"
                    )
            elif param == "save":
                logger.debug(f"Value {value} not set in {location}.")


def _validate_bool(config: dict, param: str, default: bool, location: str) -> bool:
    """Validate a boolean in the endpoint config.

    Parameters
    ----------
    config:
        The config containing the parameter
    param:
        The name of the parameter in config
    default:
        The default value for the parameter, if not present
    location:
        The location of the config, for error message.

    Returns
    -------
    bool
        The value of the parameter, or the default if the parameter didn't exist.
    """
    if param not in config:
        return default

    # We're deferring here to PyYAML as to what constitutes a boolean value in YAML.
    #
    # PyYAML seems to convert any of these strings to a boolean (the Norway problem):
    #
    #   yes Yes YES no No NO true True TRUE false False FALSE on On ON off Off OFF
    #
    # which is every boolean representation indicated by YAML-1.1 except the single
    # character representations (y n Y N) which PyYAML leaves as strings.
    if not isinstance(config[param], bool):
        raise click.ClickException(f"expected boolean for {param!r} in {location}")

    return config[param]


def validate_endpoint(config: dict, groups: dict, state) -> dict:
    """Vet and rationalise endpoint config.

    If the endpoint can't be rationalized, leaving it invalid,
    raises ClickException.

    Parameters
    ----------
    config:
        The endpoint config read from coco's config
    groups:
        The cocod group config
    state:
        The loaded state

    Returns
    -------
    dict
        The rationalised config.
    """
    from .result import TYPES as RESULT_TYPES

    # Used in error messages
    location = f"endpoint {config['name']!r}"

    # The fixed-up endpoint config will end up here
    endpoint = {"name": config["name"]}

    # this is all the allowed endpoint parameters
    ENDPOINT_PARAMETERS = (
        "after",
        "before",
        "call",
        "callable",
        "call_on_start",
        "description",
        "enforce_group",
        "get_state",
        "group",
        "report_latency",
        "report_type",
        "save_state",
        "schedule",
        "send_state",
        "set_state",
        "timestamp",
        "type",
        "values",
    )

    # Complain about extra keys in the config
    for key in config:
        if key == "name":
            continue  # Not part of endpoint format
        _validate_enum(
            f"parameter {key!r}", key, ENDPOINT_PARAMETERS, location=location
        )

    # Set default description if none given.
    endpoint["description"] = config.get("description", "NO DESCRIPTION")

    # Handle bools with defaults
    endpoint["callable"] = _validate_bool(config, "callable", True, location)
    endpoint["call_on_start"] = _validate_bool(config, "call_on_start", False, location)
    endpoint["enforce_group"] = _validate_bool(config, "enforce_group", False, location)
    endpoint["report_latency"] = _validate_bool(
        config, "report_latency", True, location
    )

    # Some enums
    endpoint["report_type"] = _validate_enum(
        "report_type",
        config.get("report_type", "CODES_OVERVIEW"),
        RESULT_TYPES,
        location=location,
    )
    endpoint["type"] = _validate_enum(
        "type", config.get("type", "GET"), ("GET", "POST"), location=location
    )

    # Check group
    have_group = "group" in config
    if have_group:
        if config["group"] not in groups:
            raise click.ClickException(
                f"host group {config['group']!r} used by {location} is unknown."
            )
        endpoint["group"] = config["group"]

    # Need at least one of "call" or "group"
    if "call" not in config and not have_group:
        raise click.ClickException(
            f"missing parameter 'group' in {location}. Or external forward "
            "needs to be disabled by including 'call: forward: null'."
        )

    if "call" in config:
        call = config["call"]
        # Check type
        if not isinstance(call, dict):
            raise click.ClickException(f"expected mapping for 'call' in {location}")

        # Unless external forwards are _explicitly_ disabled, an endpoint must
        # have a group.
        if not have_group:
            if "forward" not in call:
                # i.e. an implicit external forward.  A group is needed, or the
                # implicit forward needs to be explicitly disabled.
                raise click.ClickException(
                    f"missing parameter 'group' in {location}. Or external forward "
                    "needs to be disabled by including 'call: forward: null'."
                )
            if call["forward"] is not None:
                raise click.ClickException(
                    f"external forwards defined with no 'group' in {location}"
                )

        endpoint["call"] = {}

        # Check external forwards.
        if "forward" in call:
            endpoint["call"]["forward"] = _validate_forwards(
                location, call["forward"], "external forward"
            )

        # Check internal forwards.  Unlike external forwards, here an explicit
        # null/None is equivalent to omitting the block.
        if call.get("coco"):
            endpoint["call"]["coco"] = _validate_forwards(
                location, call["coco"], "internal forward"
            )

    # Check before and after actions
    if "before" in config:
        endpoint["before"] = _validate_forwards(
            location, config["before"], "before action"
        )
    if "after" in config:
        endpoint["after"] = _validate_forwards(
            location, config["after"], "after action"
        )

    # Validate endpoint values
    if "values" in config:
        values = config["values"]
        if not isinstance(values, dict):
            raise click.ClickException(f"expected mapping for 'values' in {location}")

        for value, type_ in values.items():
            _validate_enum(
                f"type for value {value!r}",
                type_,
                tuple(VALUE_TYPE),
                location=location,
            )

        endpoint["values"] = values
    else:
        # For later access
        values = {}

    # Timestamp path check
    if "timestamp" in config:
        if not isinstance(config["timestamp"], (str, int, float)):
            raise click.ClickException(f"expected string for 'timestamp' in {location}")
        endpoint["timestamp"] = str(config["timestamp"])

        if state.find_or_create(endpoint["timestamp"]):
            logger.warning(
                f"State '/{endpoint['timestamp']}' is not empty and "
                f"{location} will overwrite it with timestamps."
            )

    # Check all the various state interactions
    if "save_state" in config:
        save_state = config["save_state"]

        if not isinstance(save_state, list):
            save_state = [save_state]

        # If a save is to happen, values must be defined
        if not values:
            raise click.ClickException(f"'save_state' with no 'values' in {location}")

        # Check that the value types are correct
        for path in save_state:
            _validate_state_values(path, state, values, "save", location)

        endpoint["save_state"] = save_state

    if "send_state" in config:
        # Unlike with save_state, send_state can be used without values
        _validate_state_values(config["send_state"], state, values, "send", location)
        endpoint["send_state"] = config["send_state"]

    if "set_state" in config:
        if not isinstance(config["set_state"], dict):
            raise click.ClickException(
                f"expected mapping for 'set_state' in {location}"
            )
        endpoint["set_state"] = config["set_state"]

    if "get_state" in config:
        if not isinstance(config["get_state"], str):
            raise click.ClickException(f"expected string for 'get_state' in {location}")
        endpoint["get_state"] = config["get_state"]

    # Schedule checks
    if "schedule" in config:
        schedule = config["schedule"]

        # Can't schedule an endpoint that has input values
        if values:
            raise click.ClickException(
                f"cannot use both 'schedule' and 'values' in {location}"
            )

        _validate_dict(schedule, "schedule", ("period", "require_state"), location)

        if "period" not in schedule:
            raise click.ClickException(f"'schedule' missing 'period' in {location}")

        # Convert period to seconds
        try:
            period = str2total_seconds(schedule["period"])
        except ValueError as e:
            raise click.ClickException(
                f"unparsable 'schedule.period' in {location}"
            ) from e
        if not period or period < 0:
            raise click.ClickException(
                f"'schedule.period' must be positive in {location}"
            )
        # Store total seconds back into the config
        schedule["period"] = period

        if "require_state" in schedule:
            requirements = schedule["require_state"]
            if not isinstance(requirements, list):
                requirements = [requirements]

            for requirement in requirements:
                _validate_dict(
                    requirement,
                    "schedule.require_state",
                    ("path", "type", "value"),
                    location,
                )

                if "path" not in requirement:
                    raise click.ClickException(
                        f"'path' missing from 'schedule.require_state' in {location}"
                    )
                if "type" not in requirement:
                    raise click.ClickException(
                        f"'type' missing from 'schedule.require_state' in {location}"
                    )
                _validate_enum(
                    "'require_state' type in 'schedule'",
                    requirement["type"],
                    tuple(VALUE_TYPE),
                    location=location,
                )
            schedule["require_state"] = requirements

        endpoint["schedule"] = schedule

    # Endpoint config passed validation
    return endpoint
