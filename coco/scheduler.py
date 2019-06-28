"""
coco scheduler module.

Takes care of periodically called endpoints.
"""

import asyncio
from pydoc import locate
from time import time
import logging
from aiohttp import request
from sys import exit

from .util import str2total_seconds

logger = logging.getLogger(__name__)


class Scheduler(object):
    """
    Scheduler for periodically called coco endpoints.

    Each endpoint with a 'schedule' config block get a concurrent timer.
    """

    tasks = []
    timers = []

    def __init__(self, endpoints, host, port, log_level="INFO"):
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
        logger.setLevel(log_level)
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
                # Check for values
                if edpt.values is not None:
                    raise ValueError(
                        f"Endpoint '{edpt.name}' cannot be scheduled with a 'values' config block."
                    )
                # Get period
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
                # Create timer
                timer = EndpointTimer(period, edpt, self.host, self.port)
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
        self._check = []
        super().__init__(endpoint.name, period)

    def add_condition(self, condition):
        try:
            path = condition["path"]
            val = condition["value"]
            val_type = locate(condition["type"])
        except KeyError:
            raise KeyError(
                f"Endpoint '{self.name}' conditions must have all of 'path', 'value', 'type'."
            )
        if val_type is None:
            raise ValueError(f"'require_state' of endpoint {self.name} is of unknown type.")
        self._check.append({"path": path, "value": val_type(val), "type": val_type})

    async def _call(self):
        # logger.debug(f"{self.name}: {time() - self._start_t}")

        # Check conditions are satisfied
        for c in self._check:
            cast = c["type"]
            try:
                state_val = cast(self.endpoint.state.read(c["path"]))
            except KeyError:
                logger.info(
                    f"Skipping scheduled endpoint {self.name} because {c['path']} doesn't exist."
                )
                return
            if state_val != c["value"]:
                logger.info(
                    f"Skipping scheduled endpoint '{self.name}'' because {c['path']} != {c['value']}."
                )
                return
        # Send request to coco
        url = f"http://{self.host}:{self.port}/{self.name}"
        try:
            async with request(self.endpoint.type, url) as r:
                r.raise_for_status()
        except BaseException as e:
            logger.error(
                f"Scheduler failed calling {self.name}: ({e}). Has coco's sanic server crashed?"
            )
            exit(1)
