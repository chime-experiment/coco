"""
coco scheduler module.

Takes care of periodically called endpoints.
"""

import asyncio
from time import time
import logging
from aiohttp import request

logger = logging.getLogger(__name__)


class Scheduler(object):

    tasks = []
    timers = []

    def __init__(self, endpoints, host, port):
        self.host, self.port = host, port
        # find endpoints to schedule
        self._gen_timers(endpoints)

    async def start(self):
        self.tasks = []
        for timer in self.timers:
            logger.info(f"Setting timer '{timer.name}'' every {timer.period} s.")
            task = asyncio.create_task(timer.run())
            self.tasks.append(task)
            await task

    def stop(self):
        for task in self.tasks:
            task.cancel()
        exit(1)

    def _gen_timers(self, endpoints):
        if len(self.timers) > 0:
            raise Exception("Timers already exist.")

        for edpt in endpoints.values():
            if edpt.schedule is not None:
                try:
                    period = edpt.schedule["period"]
                except KeyError:
                    raise ValueError(
                        f"Endpoint '{edpt.name}' schedule block must include 'period'."
                    )
                timer = EndpointTimer(period, edpt, self.host, self.port)
                self.timers.append(timer)


class Timer(object):

    def __init__(self, name, period):
        self.name = name
        self.period = period
        self._last_t = time()
        self._start_t = self._last_t

    async def run(self):
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
        pass

    def _wait_time(self):
        return self.period - (time() - self._last_t)


class EndpointTimer(Timer):

    def __init__(self, period, endpoint, host, port):
        self.endpoint = endpoint
        self.host, self.port = host, port
        super().__init__(endpoint.name, period)

    async def _call(self):
        # TODO check result
        await self.endpoint.client_call_async(self.host, self.port)
