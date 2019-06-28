"""
coco scheduler module.

Takes care of periodically called endpoints.
"""

import asyncio
import json
from copy import copy
from time import time
import logging
from aiohttp import request, ServerTimeoutError

from .util import str2total_seconds

logger = logging.getLogger(__name__)


class Scheduler(object):
    """
    Scheduler for periodically called coco endpoints.

    Each endpoint with a 'schedule' config block get a concurrent timer.
    """

    tasks = []
    timers = []

    def __init__(self, endpoints, host, port):
        """
        Construct scheduler.

        Parameters
        ----------
        endpoints : dict of Endpoint
            All endpoints configured on coco.
        host : str
            Hostname for coco.
        port : int
            Port for coco.
        """
        self.host, self.port = host, port
        # find endpoints to schedule
        self._gen_timers(endpoints)

    async def start(self):
        """Start the scheduler (async)."""
        self.tasks = []
        for timer in self.timers:
            logger.debug(f"Setting timer '{timer.name}' every {timer.period} s.")
            task = asyncio.create_task(timer.run())
            self.tasks.append(task)
        await asyncio.gather(*self.tasks)

    def stop(self):
        """Stop the scheduler. Cancels all timer tasks."""
        for task in self.tasks:
            task.cancel()

    def _gen_timers(self, endpoints):
        if len(self.timers) > 0:
            raise Exception("Timers already exist.")

        for edpt in endpoints.values():
            if edpt.schedule is not None:
                if edpt.values is not None:
                    raise ValueError(
                        f"Endpoint '{edpt.name}' cannot be scheduled with a 'values' config block."
                    )
                try:
                    period = edpt.schedule["period"]
                except KeyError:
                    raise ValueError(
                        f"Endpoint '{edpt.name}' schedule block must include 'period'."
                    )
                period = str2total_seconds(period)
                if period is None or period == 0:
                    raise ValueError(
                        f"Could not parse 'period' parameter for endpoint {edpt.name}"
                    )
                timer = EndpointTimer(period, edpt, self.host, self.port)
                self.timers.append(timer)


class Timer(object):
    """Asynchronous timer."""

    def __init__(self, name, period):
        self.name = name
        self.period = period
        self._last_t = time()
        self._start_t = self._last_t

    async def run(self):
        """Start the timer (async)."""
        while True:
            t = self._wait_time()
            if t > 0:
                try:
                    await asyncio.sleep(t)
                except asyncio.CancelledError:
                    logger.debug(f"Cancelled timer '{self.name}''.")
                    break
            self._last_t = time()
            await self._call()

    async def _call(self):
        """Override this method with whatever the timer does."""
        pass

    def _wait_time(self):
        """Time to wait until next execution."""
        return self.period - (time() - self._last_t)


class EndpointTimer(Timer):
    """Timer that calls a coco endopint."""

    def __init__(self, period, endpoint, host, port):
        self.endpoint = endpoint
        self.host, self.port = host, port
        super().__init__(endpoint.name, period)

    async def _call(self):
        # logger.debug(f"{self.name}: {time() - self._start_t}")

        # Send request to coco
        url = f"http://{self.host}:{self.port}/{self.name}"
        try:
            async with request(self.endpoint.type, url) as r:
                if r.status != 200:
                    # TODO send to slack?
                    logger.error(
                        f"Scheduled endpoint call ({self.name}) failed: {await r.text()}."
                    )
                    return
        except ServerTimeoutError:
            # TODO send to slack?
            logger.error(f"Coco timed out at endpoint {self.name}.")
            return
