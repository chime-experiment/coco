"""
coco scheduler module.

Takes care of periodically called endpoints.
"""

import asyncio
from time import time
import logging
from aiohttp import request, ClientTimeout
from sys import exit

from .util import str2total_seconds
from .condition import Condition

logger = logging.getLogger(__name__)


class Scheduler(object):
    """
    Scheduler for periodically called coco endpoints.

    Each endpoint with a 'schedule' config block get a concurrent timer.
    """

    tasks = []
    timers = []

    def __init__(self, endpoints, host, port, frontend_timeout, log_level="INFO"):
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
        frontend_timeout : int
            Seconds before coco sanic frontend times out.
        """
        logger.setLevel(log_level)
        self.host, self.port = host, port
        self.frontend_timeout = frontend_timeout

        # find endpoints to schedule
        self._gen_timers(endpoints)

    async def start(self):
        """Start the scheduler (async)."""
        self.tasks = []
        for timer in self.timers:
            logger.debug(f"Setting timer '{timer.name}' every {timer.period} s.")
            task = asyncio.ensure_future(timer.run())
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
                # Check for values
                if edpt.values is not None:
                    logger.error(
                        f"Endpoint /{edpt.name} cannot be scheduled with a 'values' config block."
                    )
                    exit(1)
                # Get period
                try:
                    period = edpt.schedule["period"]
                except KeyError:
                    logger.error(f"Endpoint /{edpt.name} schedule block must include 'period'.")
                    exit(1)
                period = str2total_seconds(period)
                if period is None or period == 0:
                    logger.error(f"Could not parse 'period' parameter for endpoint {edpt.name}")
                    exit(1)
                # Create timer
                timer = EndpointTimer(period, edpt, self.host, self.port, self.frontend_timeout)
                self.timers.append(timer)
                # Get conditions
                require_state = edpt.schedule.get("require_state", None)
                if require_state is not None:
                    if not isinstance(require_state, (list, tuple)):
                        require_state = [require_state]
                    for condition in require_state:
                        timer.add_condition(condition)


class Timer(object):
    """Asynchronous timer."""

    def __init__(self, name, period, frontend_timeout):
        self.name = name
        self.period = period
        self._last_t = time()
        self._start_t = self._last_t
        self.frontend_timeout = frontend_timeout

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
    """Timer that calls a coco endpoint."""

    def __init__(self, period, endpoint, host, port, frontend_timeout):
        self.endpoint = endpoint
        self.host, self.port = host, port
        self._check = []
        super().__init__(endpoint.name, period, frontend_timeout)

    def add_condition(self, condition):
        """
        Add a condition on the state that must be satisfied before calling the scheduled endpoint.

        Parameters
        ----------
        condition: dict
            Must include at least key 'path' indicating state field to check.
            If 'value' and 'type' are included, ensure the state has this value,
            otherwise just check it exists.
        """
        self._check.append(Condition(self.name, condition))

    async def _call(self):
        # Check conditions are satisfied
        for c in self._check:
            if not c.check(self.endpoint.state):
                logger.info(f"Skipping scheduled /{self.name} call.")
                return

        # Send request to coco
        url = f"http://{self.host}:{self.port}/{self.name}"
        try:
            async with request(
                self.endpoint.type, url, timeout=ClientTimeout(total=self.frontend_timeout)
            ) as r:
                r.raise_for_status()
        except BaseException as e:
            logger.error(
                f"Scheduler failed calling {self.name}: ({e}). Has coco's sanic server crashed?"
            )
            exit(1)
