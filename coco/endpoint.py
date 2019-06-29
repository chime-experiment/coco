"""coco endpoint module."""
from pydoc import locate
import logging
import orjson as json
import requests
from copy import copy
from . import Result

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
        self.schedule = conf.get("schedule", None)
        call = conf.get("call", None)
        if call is None:
            self.forward_name = [self.name]
            self.forward_to_coco = None
        else:
            self.forward_to_coco = call.get("coco", None)
            if self.forward_to_coco and not isinstance(self.forward_to_coco, list):
                self.forward_to_coco = [self.forward_to_coco]
            self.forward_name = call.get("forward", [self.name])
            if self.forward_name and not isinstance(self.forward_name, list):
                self.forward_name = [self.forward_name]

        if self.group is None and self.forward_name:
            logger.error(
                f"coco.endpoint: endpoint '{name}' is missing config option 'group'. Or it "
                f"needs to set 'call: forward: null'."
            )
            exit(1)

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

    async def call(self, request):
        """
        Call the endpoint.

        Returns
        -------
        :class:`Result`
            The result of the endpoint call.
        """
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
                result.embed(endpoint, await self.forwarder.call(endpoint, {}))
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

        # Forward the request to group
        if self.forward_name:
            for endpoint in self.forward_name:
                result.add_result(
                    endpoint,
                    await self.forwarder.forward(
                        endpoint, self.group, self.type, filtered_request
                    ),
                )
        # Forward the request to any other coco endpoints
        if self.forward_to_coco:
            for endpoint in self.forward_to_coco:
                result.embed(endpoint, await self.forwarder.call(endpoint, filtered_request))

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
                result.embed(endpoint, await self.forwarder.call(endpoint, {}))
                # TODO: run these concurrently?

        if self.get_state:
            result.state(self.state.read(self.get_state))

        return result

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
            result = requests.request(self.type, url, data=json.dumps(data))
        except BaseException as e:
            return f"coco-client: {e}"
        else:
            return result.json()
