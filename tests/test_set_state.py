"""Test endpoint config option `set_state` and `get_state`."""

import pytest

from coco.util import hash_dict


@pytest.fixture
def runner(coco_runner):
    """A configured coco_runner."""

    coco_runner.add_targets("test", 1, callback=lambda path, data: data)
    coco_runner.add_config(exclude_from_reset=["excluded/from/reset"])
    coco_runner.add_endpoint("getall", {"call": {"forward": None}, "get_state": "/"})
    coco_runner.add_endpoint(
        "set", {"call": {"forward": None}, "set_state": {"test_state": True}}
    )
    coco_runner.add_endpoint(
        "set_int", {"call": {"forward": None}, "set_state": {"test_state": 5}}
    )
    coco_runner.add_endpoint(
        "set_dict",
        {
            "call": {"forward": None},
            "set_state": {"test_state": {"s": {"n": {"a": "fu"}}}},
        },
    )
    coco_runner.add_endpoint(
        "set_excluded_state",
        {
            "call": {"forward": None},
            "set_state": {"excluded/from/reset": 5},
        },
    )
    coco_runner.add_endpoint(
        "get", {"call": {"forward": None}, "get_state": "test_state"}
    )
    coco_runner.add_endpoint(
        "get_excluded_state",
        {"call": {"forward": None}, "get_state": "excluded/from/reset"},
    )
    coco_runner.add_endpoint(
        "check_hash",
        {
            "group": "test",
            "values": {"data": "str"},
            "call": {
                "forward": {"name": "hash", "reply": {"state_hash": {"data": "/"}}}
            },
        },
    )
    coco_runner.add_endpoint(
        "check_hash2",
        {
            "group": "test",
            "values": {"data": "str"},
            "call": {
                "forward": {
                    "name": "hash",
                    "reply": {"state_hash": {"data": "test_state/s/n"}},
                }
            },
        },
    )
    coco_runner.add_endpoint(
        "check_state",
        {
            "group": "test",
            "values": {"data": "str"},
            "call": {
                "forward": {
                    "name": "hash",
                    "reply": {"state": {"data": "test_state/s/n/a"}},
                }
            },
        },
    )
    coco_runner.add_endpoint(
        "check_state2",
        {
            "group": "test",
            "values": {"n": "dict"},
            "call": {"forward": {"name": "hash", "reply": {"state": "test_state/s/"}}},
        },
    )

    return coco_runner


def test_get_state(runner):
    """Test get/set_state."""

    # Set state to True
    runner.client("set")

    # Get state and compare
    response = runner.client("get", decode=True)
    assert "state" in response
    assert "test_state" in response["state"]
    assert response["state"]["test_state"] is True

    # Set state to INT
    runner.client("set_int")

    # Get state and compare
    response = runner.client("get", decode=True)
    assert "state" in response
    assert "test_state" in response["state"]
    assert response["state"]["test_state"] == 5

    # Test passing check against state hash
    response = runner.client(
        "-r", "FULL", "check_hash", "--data", hash_dict({"test_state": 5}), decode=True
    )
    assert "failed_checks" not in response

    # Test failing check against state hash
    response = runner.client(
        "-r", "FULL", "check_hash", "--data", hash_dict({"foo": 5}), decode=True
    )
    assert "failed_checks" in response
    assert "hash" in response["failed_checks"]
    for r in response["failed_checks"]["hash"].values():
        assert r == {"reply": {"mismatch_with_state_hash": ["data"]}}

    response = runner.client(
        "-r", "FULL", "check_hash", "--data", hash_dict({"test_state": 4}), decode=True
    )
    assert "failed_checks" in response
    assert "hash" in response["failed_checks"]
    for r in response["failed_checks"]["hash"].values():
        assert r == {"reply": {"mismatch_with_state_hash": ["data"]}}

    # The same for a part of the state:
    runner.client("set_dict")
    # Test passing check against partly state hash
    response = runner.client(
        "check_hash2", "--data", hash_dict({"a": "fu"}), decode=True
    )
    assert "failed_checks" not in response

    # Test failing check against partly state hash
    response = runner.client(
        "-r", "FULL", "check_hash2", "--data", hash_dict({"a": "foo"}), decode=True
    )
    assert "failed_checks" in response
    assert "hash" in response["failed_checks"]
    for r in response["failed_checks"]["hash"].values():
        assert r == {"reply": {"mismatch_with_state_hash": ["data"]}}

    # Test checks against state
    # Test passing check against part of state
    response = runner.client("check_state", "--data=fu", decode=True)
    assert "failed_checks" not in response

    # Test failing check against part of state
    response = runner.client("-r", "FULL", "check_state", "--data=f00", decode=True)
    assert "failed_checks" in response
    assert "hash" in response["failed_checks"]
    for r in response["failed_checks"]["hash"].values():
        assert r == {"reply": {"mismatch_with_state": ["data"]}}

    response = runner.client("-r", "FULL", "check_state", "--data=", decode=True)
    assert "failed_checks" in response
    assert "hash" in response["failed_checks"]
    for r in response["failed_checks"]["hash"].values():
        assert r == {"reply": {"mismatch_with_state": ["data"]}}

    # Test passing check against state
    response = runner.client("check_state2", "-n", '{"a": "fu"}', decode=True)
    assert "failed_checks" not in response

    # Test failing check against state
    response = runner.client(
        "-r", "FULL", "check_state2", "-n", '{"n": {"a": 0}}', decode=True
    )
    assert "failed_checks" in response
    assert "hash" in response["failed_checks"]
    for r in response["failed_checks"]["hash"].values():
        assert r == {"reply": {"mismatch_with_state": ["all"]}}

    response = runner.client(
        "-r", "FULL", "check_state2", "-n", '{"aa": "fu"}', decode=True
    )
    assert "failed_checks" in response
    assert "hash" in response["failed_checks"]
    for r in response["failed_checks"]["hash"].values():
        assert r == {"reply": {"mismatch_with_state": ["all"]}}

    response = runner.client("-r", "FULL", "check_state2", "-n", "{}", decode=True)
    assert "failed_checks" in response
    assert "hash" in response["failed_checks"]
    for r in response["failed_checks"]["hash"].values():
        assert r == {"reply": {"mismatch_with_state": ["all"]}}


def test_reset_state(runner):
    runner.client("set_int")
    response = runner.client("get", decode=True)
    assert "state" in response
    assert "test_state" in response["state"]
    assert response["state"]["test_state"] == 5

    runner.client("set_excluded_state")
    response = runner.client("get_excluded_state", decode=True)
    assert "state" in response
    r = response["state"]
    for p in ("excluded", "from", "reset"):
        assert p in r
        r = r[p]
    assert r == 5

    runner.client("reset-state")
    response = runner.client("get", decode=True)
    assert "status_code" in response
    assert response["status_code"] == 500  # path not found

    response = runner.client("get_excluded_state", decode=True)
    assert "state" in response
    r = response["state"]
    for p in ("excluded", "from", "reset"):
        assert p in r
        r = r[p]
    assert r == 5
