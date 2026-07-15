"""Test monitoring the coco queue length."""

import time


def waiting_callback(path, data):
    """Reply only after waiting."""

    # Wait...
    time.sleep(1)
    return data


def test_qlen(coco_runner):
    """Test the /qlen route."""

    # The "clean" targets don't wait.
    # The "waiting" targets do.
    coco_runner.add_targets("clean", 1)
    coco_runner.add_targets("waiting", 1, callback=waiting_callback)

    coco_runner.add_endpoint("waiting", {"group": "waiting"})
    coco_runner.add_endpoint("clean", {"group": "clean"})
    coco_runner.start_daemon()

    # Check for clean daemon start
    assert coco_runner.port is not None

    # Queue starts empty
    response, text = coco_runner.call_endpoint("qlen")
    assert response.status == 200
    assert int(text) == 0

    # Connect to fakeredis
    redis = coco_runner.redis_conn()

    # Directly add some stuff to the queue
    NUM_REQ = 7
    for _ in range(NUM_REQ):
        now = time.perf_counter()
        tag = f"0-{now}"
        redis.hset(
            tag,
            mapping={
                "method": "GET",
                "endpoint": "waiting",
                "request": "",
                "params": "",
                "received": now,
            },
        )
        redis.rpush("queue", tag)

    # Check queue
    response, text = coco_runner.call_endpoint("qlen")
    assert response.status == 200
    assert int(text) == NUM_REQ - 1  # The qworker popped one

    # Can the client see this number?
    result = coco_runner.client("clean")
    assert "requests in the queue" in result.stdout
