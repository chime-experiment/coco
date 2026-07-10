"""Test the internal WAIT endpoint.  Also test timestamps."""

import time


def test_wait(coco_runner):
    """Test the wait endpoint."""

    coco_runner.add_targets("test", 2)
    coco_runner.add_endpoint(
        "test",
        {
            "group": "test",
            "values": {"foo": "int", "bar": "str"},
            "call": {"coco": {"name": "wait", "request": {"duration": "2s"}}},
        },
    )

    t0 = time.monotonic()
    response = coco_runner.client(
        "-r", "FULL", "test", "--foo=0", "--bar=1337", decode=True
    )
    t1 = time.monotonic()
    assert t1 - t0 > 2
    assert t1 - t0 < 5

    assert "test" in response
    for t in coco_runner.targets:
        assert t.hit_count("/test") == 1
        h = f"http://127.0.0.1:{t.port}/"
        assert h in response["test"]
        assert "status" in response["test"][h]
        assert response["test"][h]["status"] == 200


def test_timestamp(coco_runner):
    """Test timestamps"""

    coco_runner.add_targets("test", 2, callback=lambda path, data: data)
    coco_runner.add_endpoint(
        "ts_endpt", {"group": "test", "timestamp": "timestamp/test"}
    )
    coco_runner.add_endpoint(
        "get_ts_endpt", {"group": "test", "get_state": "timestamp/test"}
    )

    response = coco_runner.client("ts_endpt", decode=True)
    assert "ts_endpt" in response
    for t in coco_runner.targets:
        assert t.hit_count("/ts_endpt") == 1

    response = coco_runner.client("-r", "FULL", "get_ts_endpt", decode=True)
    for t in coco_runner.targets:
        assert t.hit_count("/get_ts_endpt") == 1

    assert "get_ts_endpt" in response
    assert "state" in response
    assert "timestamp" in response["state"]
    assert "test" in response["state"]["timestamp"]
    timestamp = response["state"]["timestamp"]["test"]
    assert isinstance(timestamp, float)

    # This timestamps should be fresh. Test that it's between 0 and 10s old.
    assert time.time() - timestamp > 0
    assert time.time() - timestamp < 10
