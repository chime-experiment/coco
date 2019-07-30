"""coco endpoint module."""
import logging
from copy import copy
import time
from typing import Optional, Callable, Union, List, Dict

import orjson as json
from pydoc import locate
import requests
import sanic

from . import Result, ExternalForward, CocoForward
from . import (
    Check,
    ValueReplyCheck,
    TypeReplyCheck,
    IdenticalReplyCheck,
    StateHashReplyCheck,
    StateReplyCheck,
)
from .exceptions import ConfigError, InvalidUsage

ON_FAILURE_ACTIONS = ["call", "call_single_host"]

# Module level logger, note that there is also a class level, endpoint specific
# logger
logger = logging.getLogger(__name__)


class Endpoint:
    """
    An endpoint.

    Does whatever the config says.
    """

    def __init__(self, name, conf, forwarder, state):
        logger.debug(f"Loading {name}.conf")
        self.name = name
        if conf is None:
            conf = dict()
        self.description = conf.get("description", "")
        self.type = conf.get("type", "GET")
        self.group = conf.get("group")
        self.callable = conf.get("callable", False)
        self.slack = conf.get("slack")
        self.slacker = slacker
        self.call_on_start = conf.get("call_on_start", False)
        self.forwarder = forwarder
        self.state = state
        self.report_type = conf.get("report_type", "CODES_OVERVIEW")
        self.values = copy(conf.get("values", None))
        self.get_state = conf.get("get_state", None)
        self.send_state = conf.get("send_state", None)
        self.save_state = conf.get("save_state", None)
        self.set_state = conf.get("set_state", None)
        self.schedule = conf.get("schedule", None)
        self.enforce_group = bool(conf.get("enforce_group", False))
        self.forward_checks = dict()

        # Setup the endpoint logger
        self.logger = logging.getLogger(f"{__name__}.{self.name}")

        if self.values:
            for key, value in self.values.items():
                self.values[key] = locate(value)
                if self.values[key] is None:
                    raise RuntimeError(
                        f"Value {key} of endpoint {name} is of unknown type " f"{value}."
                    )

        if not self.state:
            return

        # To hold forward calls: first external ones than internal (coco) endpoints.
        self.has_external_forwards = False
        self._load_calls(conf.get("call", None))

        self.before = list()
        self.after = list()
        self._load_internal_forward(conf.get("before"), self.before)
        self._load_internal_forward(conf.get("after"), self.after)

        self.timestamp_path = conf.get("timestamp", None)
        if self.timestamp_path:
            if self.state.find_or_create(self.timestamp_path):
                logger.info(
                    f"`{self.timestamp_path}` is not empty. /{name} will overwrite "
                    f"it with timestamps."
                )

        if self.save_state:
            if isinstance(self.save_state, str):
                self.save_state = [self.save_state]
            # Check if state path exists
            for save_state in self.save_state:
                path = self.state.find_or_create(save_state)
                if not path:
                    self.logger.debug(
                        f"state path `{save_state}` configured in `save_state` for "
                        f"endpoint `{name}` is empty."
                    )

                # If save_state is set, the configured values have to match.
                if self.values:
                    # Check if endpoint value types match the associated part of the saved state
                    for key in self.values.keys():
                        try:
                            if not isinstance(path[key], self.values[key]):
                                raise RuntimeError(
                                    f"Value {key} in configured initial state at /{save_state}/ "
                                    f"has type {type(path[key]).__name__} "
                                    f"(expected {self.values[key].__name__})."
                                )
                        except KeyError:
                            # That the values are being saved in the state doesn't mean they need to
                            # exist in the initially loaded state, but write a debug line.
                            self.logger.debug(
                                f"Value {key} not found in configured initial state at "
                                f"/{save_state}/."
                            )
                        except TypeError:
                            raise ConfigError(
                                f"Value {key} has unknown type {self.values[key]} in "
                                f"config of endpoint /{self.name}."
                            )
                else:
                    self.logger.warning(
                        f"{self.name}.conf has set save_state ({save_state}), but no "
                        f"values are listed. This endpoint will ignore all data sent to it."
                    )

        # If send_state is set, the configured values have to match.
        if self.send_state:
            # Check if state path exists
            path = self.state.find_or_create(self.send_state)
            if not path:
                self.logger.warning(
                    f"state path `{self.send_state}` configured in "
                    f"`send_state` for endpoint `{name}` is empty."
                )

            if self.values:
                # Check if endpoint value types match the associated part of the send_state
                for key in self.values.keys():
                    try:
                        if not isinstance(path[key], self.values[key]):
                            raise RuntimeError(
                                f"Value {key} in configured initial state at /{self.send_state}/ "
                                f"has type {type(path[key]).__name__} "
                                f"(expected {self.values[key].__name__})."
                            )
                        # It exists both in the values and the state
                        self.logger.debug(
                            f"Value {key} is required by this endpoint so it will never "
                            f"get sent from state (the key was found in both `values` "
                            f"and in `send_state`)."
                        )
                        # TODO: Add an option to overwrite values only if present in request?
                    except KeyError:
                        # That the values are being sent from the state doesn't mean they need to
                        # exist in the value list.
                        pass

        # Check if get state path exists
        if self.get_state:
            path = self.state.find_or_create(self.get_state)
            if not path:
                self.logger.warning(
                    f"state path `{self.get_state}` configured in "
                    f"`get_state` for endpoint `{name}` is empty."
                )

    def _load_internal_forward(self, dict_, list_):
        """
        Load Forward's from the config dictionary, generate objects and place in list.

        Parameters
        ----------
        dict_ : Dict, str, List[Dict] or List[str]
            Config dict(s) describing an internal forward or just string(s) with endpoint name.
        list_ : List[CocoForward]
            The list to save the Forward objects in.
        """
        if not dict_:
            return
        if not isinstance(dict_, list):
            dict_ = [dict_]

        for f in dict_:
            if isinstance(f, dict):
                try:
                    name = f["name"]
                except KeyError:
                    raise ConfigError(
                        f"Found and internal forwarding block in {self.name}.cong that is missing "
                        f"field 'name'."
                    )
                try:
                    request = f.pop("request")
                except KeyError:
                    request = None

                list_.append(
                    CocoForward(name, self.forwarder, None, request, self._load_checks(f))
                )
            else:
                if not isinstance(f, str):
                    raise ConfigError(
                        f"Found '{type(f)}' in {self.name}.conf in an internal forwarding block "
                        f"(expected str or dict)."
                    )
                list_.append(CocoForward(f, self.forwarder, None, None, None))

    def _load_calls(self, forward_dict):
        """Parse the dict from forwarding config and save the Forward objects."""
        self.forwards_external = list()
        self.forwards_internal = list()
        if forward_dict is None:
            if self.group is None:
                raise ConfigError(
                    f"'{self.name}.conf' is missing config option 'group'. Or "
                    f"it needs to set 'call: forward: null'."
                )
            self.forwards_external.append(
                ExternalForward(self.name, self.forwarder, self.group, None, None)
            )
            self.has_external_forwards = True
        else:
            # External forwards
            forward_ext = forward_dict.get("forward", [self.name])
            # could be a string or list(str):
            if forward_ext:
                if self.group is None:
                    raise ConfigError(
                        f"'{self.name}.conf' is missing config option 'group'. "
                        f"Or it needs to set 'call: forward: null'."
                    )
                if not isinstance(forward_ext, list):
                    forward_ext = [forward_ext]
                for f in forward_ext:
                    if isinstance(f, str):
                        self.forwards_external.append(
                            ExternalForward(f, self.forwarder, self.group, None, None)
                        )
                    # could also be a block where there are checks configured for each forward call
                    elif isinstance(f, dict):
                        try:
                            name = f["name"]
                        except KeyError:
                            raise ConfigError(
                                f"Entry in forward call from "
                                f"/{self.name} is missing field 'name'."
                            )

                        self.forwards_external.append(
                            ExternalForward(
                                name, self.forwarder, self.group, None, self._load_checks(f)
                            )
                        )
                    self.has_external_forwards = True

            # Internal forwards
            forward_to_coco = forward_dict.get("coco", None)
            self._load_internal_forward(forward_to_coco, self.forwards_internal)

    def _load_checks(self, check_dict: Dict) -> List[Check]:
        checks = list()
        if not check_dict:
            return checks
        try:
            name = check_dict["name"]
        except KeyError:
            raise ConfigError(f"Name missing from forward reply check block: {check_dict}.")

        save_to_state = check_dict.get("save_reply_to_state", None)
        if save_to_state:
            if not isinstance(save_to_state, str):
                raise ConfigError(
                    f"'save_reply_to_state' in check for '{name}' in '{self.name}"
                    f".conf' is of type '{type(save_to_state).__name__}' "
                    f"(expected str)."
                )

        on_failure = check_dict.get("on_failure", None)
        if on_failure:
            for action, endpoint in on_failure.items():
                if not isinstance(endpoint, str):
                    raise ConfigError(
                        f"'on_failure'-endpoint in forward to '{name}' in "
                        f"'{self.name}.conf' is of type "
                        f"'{type(endpoint).__name__}' (expected str)."
                    )
                if action not in ON_FAILURE_ACTIONS:
                    raise ConfigError(
                        f"Unknown 'on_failure'-action in '{name}' ('{self.name}."
                        f"conf'): {action}. Use one of {ON_FAILURE_ACTIONS}."
                    )

        reply = check_dict.get("reply", None)
        if reply:
            if not isinstance(reply, dict):
                raise ConfigError(
                    f"Value 'reply' defining checks in '{name}' has type "
                    f"{type(reply).__name__} (expected dict)."
                )

            values = reply.get("value", None)
            types = reply.get("type", None)
            identical = reply.get("identical", None)
            state = reply.get("state", None)
            state_hash = reply.get("state_hash", None)
            if not (values or types or identical or state or state_hash):
                logger.info(f"In {self.name}.conf '{name}' has a 'reply' block, but it's empty.")
                return checks
            if values:
                checks.append(
                    ValueReplyCheck(
                        name, values, on_failure, save_to_state, self.forwarder, self.state
                    )
                )
            if types:
                checks.append(
                    TypeReplyCheck(
                        name, types, on_failure, save_to_state, self.forwarder, self.state
                    )
                )
            if identical:
                checks.append(
                    IdenticalReplyCheck(
                        name, identical, on_failure, save_to_state, self.forwarder, self.state
                    )
                )
            if state:
                checks.append(
                    StateReplyCheck(
                        name, state, on_failure, save_to_state, self.forwarder, self.state
                    )
                )
            if state_hash:
                checks.append(
                    StateHashReplyCheck(
                        name, state_hash, on_failure, save_to_state, self.forwarder, self.state
                    )
                )

        return checks

    async def call(self, request, hosts=None, params=[]):
        """
        Call the endpoint.

        Returns
        -------
        :class:`Result`
            The result of the endpoint call.
        """
        success = True
        self.logger.debug("endpoint called")
        if self.enforce_group:
            hosts = None

        result = Result(self.name)

        if self.before:
            for forward in self.before:
                success_forward, result_forward = await forward.trigger(self.type, {}, hosts)
                success &= success_forward
                result.embed(forward.name, result_forward)
                # TODO: run these concurrently?

        # Only forward values we expect
        filtered_request = copy(self.values)
        if request is None:
            request = dict()
        if filtered_request:
            for key, value in filtered_request.items():
                try:
                    if not isinstance(request[key], value):
                        msg = (
                            f"{self.name} received value '{key}'' of type "
                            f"{type(request[key]).__name__} (expected {value.__name__})."
                        )
                        self.logger.info(msg)
                        return result.add_message(msg)
                except KeyError:
                    msg = f"{self.name} requires value '{key}'."
                    self.logger.info(msg)
                    return result.add_message(msg)

                # save the state change:
                if self.save_state:
                    for path in self.save_state:
                        self.state.write(path, request.get(key), key)

                filtered_request[key] = request.pop(key)

        # Send values from state if not found in request (some type checking is done in constructor
        # and when state changed)
        if self.send_state:
            send_state = self.state.read(self.send_state)
            if filtered_request:
                send_state.update(filtered_request)
            filtered_request = send_state

        # Forward the request to group and then to other coco endpoints
        # TODO: should we do that concurrently?
        for forward in self.forwards_external:
            success_forward, result_forward = await forward.trigger(
                self.type, filtered_request, hosts, params
            )
            success &= success_forward
            result.add_result(result_forward)
        for forward in self.forwards_internal:
            success_forward, result_forward = await forward.trigger(
                self.type, filtered_request, hosts, params
            )
            success &= success_forward
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
                self.logger.info(msg)
                result.add_message(msg)

        if self.after:
            for forward in self.after:
                success_forward, result_forward = await forward.trigger(self.type, {}, hosts)
                success &= success_forward
                result.embed(forward.name, result_forward)
                # TODO: run these concurrently?

        if self.get_state:
            result.state(self.state.extract(self.get_state))

        if success:
            if self.set_state:
                for path, value in self.set_state.items():
                    self.state.write(path, value)
            self.write_timestamp()

        return result

    def write_timestamp(self):
        """
        Write a Unix timestamp (float) to the state.

        Does nothing if the endpoint doesn't have a path specified in `timestamp`.
        """
        if not self.timestamp_path:
            return
        self.state.write(self.timestamp_path, time.time())
        self.logger.debug(f"/{self.name} saved timestamp to state: {self.timestamp_path}")

    def client_call(self, host, port, args):
        """
        Call from a client.

        Send a request to coco daemon at <host>. Return the reply as json or an error string.

        Parameters
        ----------
        host : str
            Address of coco daemon.
        port : int
            Port of coco daemon.
        args : :class:`Namespace`
            Is expected to include all values of the endpoint.
        """
        data = copy(self.values)
        if data:
            for key, type_ in data.items():
                data[key] = self._parse_container_arg(key, type_, vars(args)[key])
        else:
            data = dict()
        data["coco_report_type"] = args.report

        url = f"http://{host}:{port}/{self.name}"
        try:
            result = requests.request(self.type, url, json=data)
        except BaseException as e:
            return f"coco-client: Sending request failed: {e}"
        else:
            try:
                return result.json()
            except Exception:
                return {"Error": result.text}

    @staticmethod
    def _parse_container_arg(key, type_, arg):
        if type_ == list or type_ == dict:
            try:
                value = json.loads(arg)
            except json.JSONDecodeError as e:
                raise InvalidUsage(f"Failure parsing argument '{key}': {e}")
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
        type_: Union[str, List[str]],
        callable: Callable[[sanic.request.Request], Optional[dict]],
    ):
        self.name = name
        self.type = type_
        self.callable = callable
        self.schedule = None

    async def call(self, request, **kwargs):
        """Call the local endpoint."""
        return await self.callable(request)
