"""coco endpoint module."""
import logging
from . import Result

logger = logging.getLogger("asyncio")


class Endpoint:
    """
    An endpoint.

    Does whatever the config says.
    """

    def __init__(self, name, conf, slacker, forwarder):
        self.name = name
        self.type = conf.get("type", "GET")
        self.group = conf.get("group")
        self.callable = conf.get("callable", False)
        self.slack = conf.get("slack")
        self.check = conf.get("check")
        self.slacker = slacker
        self.call_on_start = conf.get("call_on_start", False)
        self.forwarder = forwarder
        self.report_type = conf.get("report_type", "CODES_OVERVIEW")

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
        result = await self.forwarder.forward(self.name, request)
        result.type = request.get("coco_report_type", self.report_type)

        if self.check:
            for check in self.check:
                endpoint = list(check.keys())[0]
                options = check[list(check.keys())[0]]
                result.embed(endpoint, await self.forwarder.call(endpoint, {}))
                # TODO: run these concurrently?

        return result
