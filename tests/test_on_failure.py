"""Test endpoint calls triggered by failures."""

from threading import Lock

count = 0
lock = Lock()


def callback(path, body):
    """Reply with the incoming json request."""
    global count

    # for /restart, just return input
    if path == "/restart":
        return body

    # When count gets to 1, return an invalid reply
    with lock:
        if count > 0:
            return {"not_ok": True}
        count += 1
        return {"ok": True}


def test_on_reply(coco_runner):
    """Test coco's on_failure option."""
    global count

    N_HOSTS = 2
    coco_runner.add_targets("test", N_HOSTS, callback=callback)
    coco_runner.add_endpoint(
        "call_single",
        {
            "group": "test",
            "call": {
                "forward": {
                    "name": "status",
                    "reply": {"type": {"ok": "bool"}},
                    "on_failure": {"call_single_host": "restart"},
                }
            },
        },
    )
    coco_runner.add_endpoint(
        "call_all",
        {
            "group": "test",
            "call": {
                "forward": {
                    "name": "status",
                    "reply": {"type": {"ok": "bool"}},
                    "on_failure": {"call": "restart"},
                }
            },
        },
    )
    coco_runner.add_endpoint("status", {"group": "test"})
    coco_runner.add_endpoint("restart", {"group": "test"})

    # Test call on failure
    response = coco_runner.client("-r", "FULL", "call_all", decode=True)
    for t in coco_runner.targets:
        assert t.hit_count("/status") == 1
        assert t.hit_count("/restart") == 1

    # Check failure report
    failed_host = list(response["failed_checks"]["status"].keys())
    assert len(failed_host) == 1
    reply = response["failed_checks"]["status"][failed_host[0]]["reply"]
    assert reply["missing"] == ["ok"]

    # reset count
    with lock:
        count = 0

    # Test call_single_host
    response = coco_runner.client("-r", "FULL", "call_single", decode=True)

    # Check failure report
    failed_host = list(response["failed_checks"]["status"].keys())
    assert len(failed_host) == 1
    reply = response["failed_checks"]["status"][failed_host[0]]["reply"]
    assert reply["missing"] == ["ok"]

    # Check only failed host called restart
    for t in coco_runner.targets:
        assert t.hit_count("/status") == 2
        # only second host should have failed
        if t.port == int(failed_host[0].strip("http://").split(":")[1]):
            assert t.hit_count("/restart") == 2
        else:
            assert t.hit_count("/restart") == 1
