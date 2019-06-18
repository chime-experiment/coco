"""
coco worker.

This module implements coco's worker. It runs in it's own process and empties the queue.
"""
import asyncio
import aioredis
import logging
import orjson as json
import signal
import sys

from . import Result

loop = asyncio.get_event_loop()
logger = logging.getLogger("asyncio")


def signal_handler(sig, frame):
    """
    Signal handler for SIGINT.

    Stops the asyncio event loop.
    """
    logger.debug("Stopping queue worker loop...")
    loop.stop()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


def main_loop(endpoints, log_level):
    """
    Wait for tasks and run them.

    Queries the redis queue for new tasks and runs them serialized until killed.

    Parameters
    ----------
    endpoints : dict
        A dict with keys being endpoint names and values being of type :class:`Endpoint`.
    """
    logger.setLevel(log_level)

    async def go():
        conn = await aioredis.create_connection(("localhost", 6379), encoding="utf-8")

        while True:
            # Wait until the name of an endpoint call is in the queue.
            name = await conn.execute("blpop", "queue", 30)
            if name is None:
                continue
            name = name[1]

            # Use the name to get all info on the call and delete from redis.
            [method, endpoint_name, request] = await conn.execute(
                "hmget", name, "method", "endpoint", "request"
            )
            request = json.loads(request)
            await conn.execute("del", name)

            try:
                endpoint = endpoints[endpoint_name]
            except KeyError:
                msg = f"endpoint /{endpoint_name} not found."
                logger.debug(f"coco.worker: Received request to /{endpoint_name}, but {msg}")
                await conn.execute(
                    "rpush",
                    f"{name}:res",
                    json.dumps(Result(endpoint_name, result=None, error=msg).report()),
                )
                continue

            if method != endpoint.type:
                msg = (
                    f"endpoint /{endpoint_name} received {method} request (accepts "
                    f"{endpoint.type} only)"
                )
                logger.debug(f"coco.worker: {msg}")
                await conn.execute(
                    "rpush",
                    f"{name}:res",
                    json.dumps(Result(endpoint_name, result=None, error=msg).report()),
                )
                continue

            logger.debug(f"coco.worker: Calling /{endpoint.name}: {request}")
            result = await endpoint.call(request)

            # Return the result
            await conn.execute("rpush", f"{name}:res", json.dumps(result.report()))

        # optionally close connection
        conn.close()

    loop.run_until_complete(go())
