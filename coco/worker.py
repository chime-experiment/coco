"""
coco worker.

This module implements coco's worker. It runs in its own process and empties the queue.
"""

import asyncio
import json
import logging
import signal
import sys
import time
import traceback
from urllib.parse import parse_qsl

from redis import asyncio as aioredis

from . import slack
from .exceptions import CocoException, InvalidMethod, InvalidPath, InvalidUsage
from .result import Result
from .scheduler import Scheduler

logger = logging.getLogger(__name__)

# Redis connection for qworker
conn = None


def signal_handler(signum, frame):
    """Signal handler."""
    global conn

    logger.debug(f"Caught signal {signum}.")
    if conn:
        conn.close()
        conn = None
    raise KeyboardInterrupt


async def _open_redis_connection(redis_port):
    try:
        return aioredis.from_url(
            f"redis://127.0.0.1:{redis_port}", encoding="utf-8", decode_responses=True
        ).client()
    except ConnectionError as e:
        logger.error(
            f"coco.worker: failure connecting to redis. Make sure it is running: {e}"
        )
        sys.exit(1)


async def go(endpoints, redis_port, metrics_port, forwarder):
    """Asynchronous qworker main loop."""
    # start the prometheus server for forwarded requests
    forwarder.start_prometheus_server(metrics_port, redis_port)
    forwarder.init_metrics()

    global conn
    conn = await _open_redis_connection(redis_port)
    code = None

    while True:
        # Wait until the name of an endpoint call is in the queue.
        name = await conn.execute_command("blpop", "queue", 30)
        if name is None:
            continue
        name = name[1]

        # check for shutdown condition
        if name == "coco_shutdown":
            logger.info("coco.worker: Received shutdown command. Exiting...")
            exit(0)

        # Use the name to get all info on the call and delete from redis.
        [
            method,
            endpoint_name,
            request,
            params,
            received,
        ] = await conn.execute_command(
            "hmget", name, "method", "endpoint", "request", "params", "received"
        )
        queue_wait = None
        if received:
            received = float(received)
            queue_wait = time.perf_counter() - received
            conn.rpush(
                "queue_wait_time",
                json.dumps({"endpoint": endpoint_name, "value": queue_wait}),
            )

        await conn.execute_command("del", name)
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
                    logger.debug(
                        f"coco.worker: Received request to /{endpoint_name}, but {msg}"
                    )
                    raise InvalidPath(msg)

            # Parse URL query parameters
            # TODO: This will be used by certain kotekan endpoints that do
            #       not accept POST but need parameters specified. If we
            #       find another scheme to make this work we should remove
            #       this feature as it is somewhat redundant with the
            #       request values.
            params = parse_qsl(params)

            try:
                endpoint = endpoints[endpoint_name]
            except KeyError as exc:
                raise InvalidPath(f"Endpoint /{endpoint_name} not found.") from exc

            # Check that it is being requested with the correct method
            if method != endpoint.type and method not in endpoint.type:
                msg = (
                    f"endpoint /{endpoint_name} received {method} request (accepts "
                    f"{endpoint.type} only)"
                )
                logger.debug(f"coco.worker: {msg}")
                raise InvalidMethod(msg)

            logger.debug(f"coco.worker: Calling /{endpoint.name}: {request}")
            result = await endpoint.call(request, params=params)

            # Transform any Result into a report so it can be serialised
            if isinstance(result, Result):
                result = result.report()
            if endpoint.report_latency:
                result["queue_wait"] = queue_wait

            code = 200

        # Process a known exception source into a response
        except CocoException as e:
            result = e.to_dict()
            code = e.status_code

        # Unexpected exceptions are returned as HTTP 500 errors, and dump a
        # traceback
        except Exception as e:
            etype = e.__class__.__qualname__
            msg = e.args[0] if e.args else None
            result = {"type": etype, "message": msg}
            code = 500  # Internal server error
            logger.exception(f"{etype} raised during endpoint processing: {msg}")

        # Always attempt to return the result so that the client doesn't hang...
        finally:
            # If processing this request took a long time,
            # the redis server may have hung up.
            try:
                await conn.execute_command("rpush", f"{name}:res", json.dumps(result))
            except aioredis.exceptions.ConnectionError as err:
                logger.debug(err)
                logger.info(
                    f"Redis connection closed while processing /{endpoint_name}. "
                    "Opening new connection..."
                )

                # open new connection and try one more time
                conn = await _open_redis_connection(redis_port)
                await conn.execute_command("rpush", f"{name}:res", json.dumps(result))
            finally:
                await conn.execute_command("rpush", f"{name}:code", code)

        # optionally close connection
        await conn.close()


def main_loop(
    app, endpoints, forwarder, coco_port, metrics_port, redis_port, frontend_timeout
):
    """
    Wait for tasks and run them.

    Queries the redis queue for new tasks and runs them serialized until killed.

    Parameters
    ----------
    app : Sanic.app
        The controlling Sanic app.
    endpoints : dict
        A dict with keys being endpoint names and values being of type
        :class:`Endpoint`.
    forwarder
        The RequestForwarder
    coco_port:
        The coco Sanic port
    metrics_port:
        The prometheus metrics port
    redis_port:
        The redis server port
    frontend_timeout : int
        Number of seconds before coco sanic frontend times out.
    """

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    shutdown = False
    try:
        # NOTE: need to create a new event loop here otherwise macOS seems to have
        # issues involving the asyncio event loop and the Process fork
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Start up slack logging for the worker
        slack.start(loop)

        scheduler = Scheduler(endpoints, "127.0.0.1", coco_port, frontend_timeout)
        loop.run_until_complete(
            asyncio.gather(
                go(endpoints, redis_port, metrics_port, forwarder), scheduler.start()
            )
        )

        # Cleanup
        loop.run_until_complete(slack.stop())
    except KeyboardInterrupt:
        # Normal termination via signal
        logger.info("qworker shutdown")
        shutdown = True
    except SystemExit:
        # qworker called sys.exit
        logger.info("qworker exiting")
        shutdown = False
    except BaseException as e:  # noqa: BLE001
        # Report all errors
        logger.error(f"qworker encountered an error: {e}")
        logger.error(traceback.format_exc())
    finally:
        if not shutdown:
            # Shutdown Sanic on abnormal exit
            app.manager.terminate()
