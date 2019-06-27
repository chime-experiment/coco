"""
coco scheduler module.

Takes care of periodically called endpoints.
"""

import asyncio
from urllib.parse import urljoin
from time import time


class Scheduler(object):

    tasks = []
    targets = []

    def __init__(self, endpoints, host, port):
        # URL of coco server
        self.coco_url = f"{host}:{port}"
        if not self.coco_url.startswith("http://"):
            self.coco_url = "http://" + self.coco_url
        # find endpoints to schedule
        self._gen_targets(endpoints)

    async def start(self):
        self.tasks = []
        for target in self.targets:
            task = asyncio.create_task(target.run())
            self.tasks.append(task)

    def stop(self):
        for task in self.tasks:
            task.cancel()

    def _gen_targets(self, endpoints):
        if len(self.targets) > 0:
            raise Exception("Targets already exist.")
        for i in range(4):
            self.targets.append(Target(f"target{i}", 5*i + 1))


class Target(object):

    def __init__(self, name, period):
        self.name = name
        self.period = period
        self.last_t = time()
        self.start_t = self.last_t

    async def run(self):
        while True:
            t = self.wait_time()
            if t > 0:
                try:
                    await asyncio.sleep(t)
                except asyncio.CancelledError:
                    print(f"Cancelled {self.name}.")
                    break
            self.last_t = time()
            await self.call()

    async def call(self):
        print(f"Calling {self.name}. Time: {time() - self.start_t}.")
        await asyncio.sleep(0.1)

    def wait_time(self):
        return self.period - (time() - self.last_t)
