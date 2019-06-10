"""
coco worker.

This module implements coco's worker. It runs in it's own process and empties the queue.
"""
import asyncio
import aioredis
import orjson as json
import signal
import sys

loop = asyncio.get_event_loop()


def signal_handler(sig, frame):
    """
    Signal handler for SIGINT.

    Stops the asyncio event loop.
    """
    print("Stopping worker loop...")
    loop.stop()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


def main_loop(endpoints):
    """
    Wait for tasks and run them.

    Queries the redis queue for new tasks and runs them serialized until killed.

    Parameters
    ----------
    endpoints : dict
        A dict with keys being endpoint names and values being of type :class:`Endpoint`.
    """
    global loop

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
                print(f"Endpoint /{endpoint_name} not found.")
                # TODO: failure response
                await conn.execute("rpush", f"{name}:res", 1)  # request["n"])
                continue

            if method != endpoint.type:
                print(
                    f"Endpoint /{endpoint_name} received {method} request (accepts "
                    f"{endpoint.type} only)"
                )
                # TODO failure response
                await conn.execute("rpush", f"{name}:res", 1)  # request["n"])
                continue

            print(f"Calling /{endpoint.name}: {request}")
            await endpoint.call(request)

            # Return the result
            await conn.execute("rpush", f"{name}:res", 1)  # request["n"])

        # optionally close connection
        conn.close()

    loop.run_until_complete(go())
