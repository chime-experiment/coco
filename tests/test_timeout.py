"""Test basic endpoint call forwarding with timeout."""

import time


def callback(path, data):
    """Reply with the incoming json request."""
    time.sleep(2)
    return data


def test_timeout_for_specific_forward(coco_runner):
    """Test endpoint timeout"""

    coco_runner.add_targets("test", 2, callback=callback)
    coco_runner.add_endpoint(
        "test",
        {
            "call": {"forward": {"name": "test", "timeout": "1s"}},
            "group": "test",
            "values": {"foo": "int", "bar": "str"},
        },
    )

    response = coco_runner.client(
        "-r", "FULL", "test", "--foo=0", "--bar=1337", decode=True
    )

    assert "test" in response
    for t in coco_runner.targets:
        h = f"http://127.0.0.1:{t.port}/"
        assert h in response["test"]
        assert "status" in response["test"][h]
        assert "reply" in response["test"][h]
        assert response["test"][h]["status"] == 0
        assert response["test"][h]["reply"] == "Timeout"
