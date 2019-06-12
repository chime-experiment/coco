"""coco endpoint module."""
from pydoc import locate
import logging
from copy import copy
from . import Result

logger = logging.getLogger("asyncio")


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
        self.check = conf.get("check")
        self.slacker = slacker
        self.call_on_start = conf.get("call_on_start", False)
        self.forwarder = forwarder
        self.state = state
        self.report_type = conf.get("report_type", "CODES_OVERVIEW")
        self.values = copy(conf.get("values", None))
        self.state_path = conf.get("state", None)

        if self.values:
            for key, value in self.values.items():
                self.values[key] = locate(value)
                if self.values[key] is None:
                    raise RuntimeError(
                        f"Value {key} of endpoint {name} is of unknown type " f"{value}."
                    )
            if self.state_path:
                # Check if endpoint value types match the associated part of the saved state
                for key in self.values.keys():
                    try:
                        if not isinstance(self.state.read(self.state_path, key), self.values[key]):
                            raise RuntimeError(
                                f"Value {key} in configured initial state at /{self.state_path}/ "
                                f"has type {type(self.state[self.state_path][key]).__name__} "
                                f"(expected {self.values[key].__name__})."
                            )
                    except KeyError:
                        raise RuntimeError(
                            f"Value {key} not found in configured initial state at "
                            f"/{self.state_path}/."
                        )

    async def call(self, request):
        """
        Call the endpoint.

        Returns
        -------
        :class:`Result`
            The result of the endpoint call.
        """
        logger.debug(f"comet.endpoint: {self.name} called")
        if self.slack:
            self.slacker.send(self.slack.get("message", self.name), self.slack.get("channel"))

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
                        logger.info(f"comet.endpoint: {msg}")
                        return Result(self.name, None, msg)
                except KeyError:
                    msg = f"endpoint {self.name} requires value '{key}'."
                    logger.info(f"comet.endpoint: {msg}")
                    return Result(self.name, None, msg)

                # save the state change:
                if self.state_path:
                    self.state.write(self.state_path, request.get(key), key)

                filtered_request[key] = request.pop(key)
        # Send values from state (type checking is done in constructor and when state changed)
        elif self.state_path:
            filtered_request = self.state.read(self.state_path)

        result = await self.forwarder.forward(self.name, filtered_request)
        result.type = request.pop("coco_report_type", self.report_type)

        # Report any additional values in the request
        for key in request.keys():
            msg = f"Found additional value '{key}' in request to /{self.name}."
            logger.info(f"comet.endpoint: {msg}")
            result.add(msg)

        if self.check:
            for check in self.check:
                endpoint = list(check.keys())[0]
                options = check[list(check.keys())[0]]
                result.embed(endpoint, await self.forwarder.call(endpoint, {}))
                # TODO: run these concurrently?

        return result
