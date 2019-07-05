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
from .scheduler import Scheduler
from .exceptions import CocoException, InvalidMethod, InvalidPath, InvalidUsage

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


def main_loop(endpoints, forwarder, coco_port, metrics_port, log_level):
    """
    Wait for tasks and run them.

    Queries the redis queue for new tasks and runs them serialized until killed.

    Parameters
    ----------
    endpoints : dict
        A dict with keys being endpoint names and values being of type :class:`Endpoint`.
    """

    async def go():

        # start the prometheus server for forwarded requests
        forwarder.start_prometheus_server(metrics_port)
        forwarder.init_metrics()

        try:
            conn = await aioredis.create_connection(("localhost", 6379), encoding="utf-8")
        except ConnectionError as e:
            logger.error(f"coco.worker: failure connecting to redis. Make sure it is running: {e}")
            exit(1)

        while True:
            # Wait until the name of an endpoint call is in the queue.
            name = await conn.execute("blpop", "queue", 30)
            if name is None:
                continue
            name = name[1]

            # check for shutdown condition
            if name == "coco_shutdown":
                logger.info("coco.worker: Received shutdown command. Exiting...")
                exit(0)

            # Use the name to get all info on the call and delete from redis.
            [method, endpoint_name, request] = await conn.execute(
                "hmget", name, "method", "endpoint", "request"
            )

            await conn.execute("del", name)

            # Call the endpoint, and handle any exceptions that occur
            try:

                if not request:
                    request = None
                else:
                    try:
                        request = json.loads(request)
                    except json.JSONDecodeError as e:
                        raise InvalidUsage(f"Invalid JSON payload: {request}") from e
                    # Check that the requested endpoint exists
                    if endpoint_name not in endpoints:
                        msg = f"endpoint /{endpoint_name} not found."
                        logger.debug(f"coco.worker: Received request to /{endpoint_name}, but {msg}")
                        raise InvalidPath(msg)

                endpoint = endpoints[endpoint_name]

                # Check that it is being requested with the correct method
                if method != endpoint.type and method not in endpoint.type:
                    msg = (
                        f"endpoint /{endpoint_name} received {method} request (accepts "
                        f"{endpoint.type} only)"
                    )
                    logger.debug(f"coco.worker: {msg}")
                    raise InvalidMethod(msg)

                logger.debug(f"coco.worker: Calling /{endpoint.name}: {request}")
                result = await endpoint.call(request)
                code = 200

            # Process a known exception source into a response
            except CocoException as e:
                result = e.to_dict()
                code = e.status_code

            # Unexpected exceptions are returned as HTTP 500 errors, and dump a
            # traceback
            except BaseException as e:
                etype = e.__class__.__qualname__
                msg = e.args[0] if e.args else None
                result = {"type": etype, "message": msg}
                code = 500  # Internal server error
                logger.exception(f"{etype} raised during endpoint processing: {msg}")

                # Normal exceptions should be supressed, BaseExceptions (e.g.
                # KeyboardInterrupt) should be re-raised
                if not isinstance(e, Exception):
                    raise e

            # Always attempt to return the result so that the client doesn't hang...
            finally:
                await conn.execute("rpush", f"{name}:res", json.dumps(result))
                await conn.execute("rpush", f"{name}:code", code)

        # optionally close connection
        conn.close()

    logger.setLevel(log_level)

    # TODO: need to create a new event loop here otherwise macOS seems to have
    # issues involving the asyncio event loop and the Process fork
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    scheduler = Scheduler(endpoints, "localhost", coco_port, log_level)
    loop.run_until_complete(asyncio.gather(go(), scheduler.start()))