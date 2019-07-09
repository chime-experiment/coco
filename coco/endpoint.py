"""coco endpoint module."""
import logging
from copy import copy
from typing import Optional, Callable, Union, List

from pydoc import locate
import requests
import sanic

from . import Result, ExternalForward, CocoForward

logger = logging.getLogger(__name__)


class Endpoint:
    """
    An endpoint.

    Does whatever the config says.
    """

    def __init__(self, name, conf, slacker, forwarder, state):
        self.name = name
        self.type = conf.get("type", "GET")
        self.group = conf.get("group")
        self.callable = conf.get("callable", False)
        self.slack = conf.get("slack")
        self.before = conf.get("before")
        self.after = conf.get("after")
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
        self.forward_checks = dict()

        # To hold forward calls: first external ones than internal (coco) endpoints.
        self.has_external_forwards = False
        self._load_forwards(conf.get("call", None))

        if self.values:
            for key, value in self.values.items():
                self.values[key] = locate(value)
                if self.values[key] is None:
                    raise RuntimeError(
                        f"Value {key} of endpoint {name} is of unknown type " f"{value}."
                    )

        if not self.state:
            return

        if self.save_state:
            # Check if state path exists
            path = self.state.find_or_create(self.save_state)
            if not path:
                logger.warning(
                    f"coco.endpoint: state path `{self.save_state}` configured in "
                    f"`save_state` for endpoint `{name}` is empty."
                )

            # If save_state is set, the configured values have to match.
            if self.values:
                # Check if endpoint value types match the associated part of the saved state
                for key in self.values.keys():
                    try:
                        if not isinstance(path[key], self.values[key]):
                            raise RuntimeError(
                                f"Value {key} in configured initial state at /{self.save_state}/ "
                                f"has type {type(path[key]).__name__} "
                                f"(expected {self.values[key].__name__})."
                            )
                    except KeyError:
                        # That the values are being saved in the state doesn't mean they need to
                        # exist in the initially loaded state, but write a debug line.
                        logger.debug(
                            f"Value {key} not found in configured initial state at "
                            f"/{self.save_state}/."
                        )
            else:
                logger.warning(
                    f"{self.name}.conf has set save_state ({self.save_state}), but no "
                    f"values are listed. This endpoint will ignore all data sent to it."
                )

        # If send_state is set, the configured values have to match.
        if self.send_state:
            # Check if state path exists
            path = self.state.find_or_create(self.send_state)
            if not path:
                logger.warning(
                    f"coco.endpoint: state path `{self.send_state}` configured in "
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
                        logger.debug(
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
                logger.warning(
                    f"coco.endpoint: state path `{self.get_state}` configured in "
                    f"`get_state` for endpoint `{name}` is empty."
                )

    def _load_forwards(self, forward_dict):
        """Parse the dict from forwarding config and save the Forward objects."""
        forwards = list()
        if forward_dict is None:
            if self.group is None:
                logger.error(
                    f"coco.endpoint: endpoint '{self.name}' is missing config option 'group'. Or "
                    f"it needs to set 'call: forward: null'."
                )
                exit(1)
            forwards.append(
                ExternalForward(
                    self.name, self.forwarder, self.group, None, self._check_forward_reply
                )
            )
            self.has_external_forwards = True
            self.forwards = forwards
        else:
            # External forwards
            forward_ext = forward_dict.get("forward", [self.name])
            # could be a string or list(str):
            if forward_ext:
                if self.group is None:
                    logger.error(
                        f"coco.endpoint: endpoint '{self.name}' is missing config option 'group'. "
                        f"Or it needs to set 'call: forward: null'."
                    )
                    exit(1)
                if not isinstance(forward_ext, list):
                    forward_ext = [forward_ext]
                for f in forward_ext:
                    if isinstance(f, str):
                        forwards.append(
                            ExternalForward(
                                f, self.forwarder, self.group, None, self._check_forward_reply
                            )
                        )
                    # could also be a block where there are checks configured for each forward call
                    elif isinstance(f, dict):
                        try:
                            name = f.pop("name")
                        except KeyError:
                            logger.error(
                                f"Entry in forward call from "
                                f"/{self.name} is missing field 'name'."
                            )
                            exit(1)

                        self.forward_checks[name] = f
                        forwards.append(
                            ExternalForward(
                                name, self.forwarder, self.group, None, self._check_forward_reply
                            )
                        )
                    self.has_external_forwards = True

            # Internal forwards
            forward_to_coco = forward_dict.get("coco", None)
            logger.info(f"Endpoint /{self.name} settings: forwarding to coco: {forward_to_coco}")
            if forward_to_coco:
                if not isinstance(forward_to_coco, list):
                    forward_to_coco = [forward_to_coco]

                for f in forward_to_coco:
                    if isinstance(f, dict):
                        try:
                            name = f.pop("name")
                        except KeyError:
                            logger.error(
                                f"Entry in forward to another coco endpoint from "
                                f"/{self.name} is missing field 'name'."
                            )
                            exit(1)
                        try:
                            request = f.pop("request")
                        except KeyError:
                            request = None
                        for field in f.keys():
                            logger.error(
                                f"Additional field '{field}' in forward from "
                                f"/{self.name} to /{name}."
                            )
                            exit(1)
                        forwards.append(
                            CocoForward(
                                name,
                                self.forwarder,
                                self.group,
                                request,
                                self._check_forward_reply,
                            )
                        )
                    else:
                        if not isinstance(f, str):
                            logger.error(
                                f"Found '{type(f)}' in configuration of /{self.name} "
                                f"in 'call/coco' (expected str or dict)."
                            )
                            exit(1)
                        forwards.append(
                            CocoForward(
                                f, self.forwarder, self.group, None, self._check_forward_reply
                            )
                        )
        self.forwards = forwards

    async def call(self, request, hosts=None):
        """
        Call the endpoint.

        Returns
        -------
        :class:`Result`
            The result of the endpoint call.
        """
        success = True
        logger.debug(f"coco.endpoint: /{self.name}")
        if self.slack:
            self.slacker.send(self.slack.get("message", self.name), self.slack.get("channel"))

        result = Result(self.name)

        if self.before:
            for check in self.before:
                if isinstance(check, str):
                    endpoint = check
                else:
                    endpoint = list(check.keys())[0]
                    options = check[list(check.keys())[0]]
                result.embed(endpoint, await self.forwarder.call(endpoint, self.type, {}, hosts))
                # TODO: run these concurrently?

        # Only forward values we expect
        filtered_request = copy(self.values)
        if filtered_request:
            for key, value in filtered_request.items():
                try:
                    if not isinstance(request[key], value):
                        msg = (
                            f"endpoint {self.name} received value '{key}'' of type "
                            f"{type(request[key]).__name__} (expected {value.__name__})."
                        )
                        logger.info(f"coco.endpoint: {msg}")
                        return result.add_message(msg)
                except KeyError:
                    msg = f"endpoint {self.name} requires value '{key}'."
                    logger.info(f"coco.endpoint: {msg}")
                    return result.add_message(msg)

                # save the state change:
                if self.save_state:
                    self.state.write(self.save_state, request.get(key), key)

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
        for forward in self.forwards:
            if not await forward.trigger(result, self.type, filtered_request, hosts):
                success = False

        # Look for result type parameter in request
        if request:
            result.type = request.pop("coco_report_type", self.report_type)
        else:
            result.type = self.report_type

        # Report any additional values in the request
        if request:
            for key in request.keys():
                msg = f"Found additional value '{key}' in request to /{self.name}."
                logger.info(f"coco.endpoint: {msg}")
                result.add_message(msg)

        if self.after:
            for check in self.after:
                if isinstance(check, str):
                    endpoint = check
                else:
                    endpoint = list(check.keys())[0]
                    options = check[list(check.keys())[0]]
                result.embed(endpoint, await self.forwarder.call(endpoint, self.type, {}, hosts))
                # TODO: run these concurrently?

        if self.get_state:
            result.state({self.get_state: self.state.read(self.get_state)})

        if success and self.set_state:
            for path, value in self.set_state.items():
                self.state.write(path, value)

        return result

    def _save_reply(self, reply, path):
        """
        Save a forward call reply to state.

        The replies of different hosts get merged.

        Parameters
        ----------
        reply : dict
            Keys are hosts and values are tuples of replies (dict) and HTTP status codes.
        """
        merged = dict()
        for r in reply.values():
            merged.update(r[0])
        self.state.write(path, merged)

    async def _check_forward_reply(self, forward_name, reply, result):
        """
        Run the defined checks on the reply of a forward call.

        Parameters
        ----------
        forward_name : str
            Name of the endpoint forwarded to.
        reply : dict
            Keys should be :class:`Host` objects and values should be tuples of (<the hosts reply
            as dict or str>, HTTP status code as int)
        result : :class:`Result`
            Result of the ongoing endpoint call.

        Returns
        -------
            `False` if any check failed, otherwise `True`.
        """
        success = True
        check_reply = self.forward_checks.get(forward_name, None)
        if check_reply is None:
            return success
        expected_reply = check_reply.get("reply", None)
        if expected_reply:
            for host, r in reply.items():
                host_reply_bad = False
                for name, condition in expected_reply.items():
                    if name not in r[0].keys():
                        msg = (
                            f"coco.endpoint: /{self.name}: failure when forwarding request to "
                            f"{host.join_endpoint(forward_name)}: expected value not found: {name}"
                        )
                        logger.debug(msg)
                        result.report_failure(forward_name, host, "missing", name)
                        host_reply_bad = True
                        success = False
                        continue
                    expected_type = condition.get("type", None)
                    if expected_type:
                        # TODO: do locate() only once on start
                        if not isinstance(r[0][name], locate(expected_type)):
                            msg = (
                                f"coco.endpoint: /{self.name}: failure when forwarding request to "
                                f"{host.join_endpoint(forward_name)}: expected value '{name}' of type: "
                                f"{type(r[0][name]).__name__} (expected {expected_type})"
                            )
                            logger.debug(msg)
                            result.report_failure(forward_name, host, "type", name)
                            host_reply_bad = True
                            success = False
                            continue
                # Check if we should there is a on_failure call to do per host:
                call_single_host = check_reply.setdefault("on_failure", dict()).get(
                    "call_single_host", None
                )
                if host_reply_bad and call_single_host:
                    logger.debug(
                        f"Calling {call_single_host} on host "
                        f"{host.url()} because {forward_name} failed."
                    )
                    result.embed(
                        call_single_host,
                        await self.forwarder.call(call_single_host, self.type, {}, [host]),
                    )

        save_to_state = check_reply.get("save_reply_to_state", None)
        if save_to_state:
            self._save_reply(reply, save_to_state)

        # Check if we should call another endpoint on failure:
        if not success:
            on_failure_endpoint = check_reply.setdefault("on_failure", dict()).get("call", None)
            if on_failure_endpoint:
                result.embed(
                    on_failure_endpoint,
                    await self.forwarder.call(on_failure_endpoint, self.type, {}),
                )
        return success

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
            for key in data.keys():
                data[key] = vars(args)[key]
        else:
            data = dict()
        data["coco_report_type"] = args.report

        url = f"http://{host}:{port}/{self.name}"
        try:
            result = requests.request(self.type, url, json=data)
        except BaseException as e:
            return f"coco-client: Sending request failed: {e}"
        else:
            return result.json()


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
