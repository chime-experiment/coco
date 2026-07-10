"""Test endpoint calls triggered by failures."""

import random
from threading import Lock

fixed_num = 0
lock = Lock()


def callback(path, body):
    """Used by the rest_server to generate data
    to send back to cocod."""

    global fixed_num

    if path == "/rand":
        # If the body has a True "rand" value, return
        # a random number.  Otherwise return a fixed number.
        with lock:
            if body["rand"]:
                rand = random.random()

                fixed_num += rand
                return {"rand": rand}
            return {"rand": fixed_num}

    # Otherwise, just return body
    return body


def test_forward(coco_runner):
    """Test coco's forward reply check."""

    # Number of targets
    N_HOSTS = 2

    # Create rest farm with the above callback
    coco_runner.add_targets("test", N_HOSTS, callback=callback)

    # Add endpoints
    coco_runner.add_endpoint(
        "type_check",
        {
            "group": "test",
            "values": {"ok": "bool"},
            "call": {"forward": {"name": "pong", "reply": {"type": {"ok": "bool"}}}},
        },
    )
    coco_runner.add_endpoint(
        "type_check_fail",
        {
            "group": "test",
            "values": {"ok": "int"},
            "call": {"forward": {"name": "pong", "reply": {"type": {"ok": "bool"}}}},
        },
    )
    coco_runner.add_endpoint(
        "value_check",
        {
            "group": "test",
            "values": {"ok": "bool"},
            "call": {"forward": {"name": "pong", "reply": {"value": {"ok": True}}}},
        },
    )
    coco_runner.add_endpoint(
        "identical_check",
        {
            "group": "test",
            "values": {"rand": "bool"},
            "call": {"forward": {"name": "rand", "reply": {"identical": ["rand"]}}},
        },
    )
    coco_runner.add_endpoint("pong", {"group": "test"})
    coco_runner.add_endpoint("rand", {"group": "test"})

    # For before check
    coco_runner.add_endpoint(
        "bvalue_check",
        {
            "group": "test",
            "values": {"ok": "bool"},
            "call": {"forward": None},
            "before": {"name": "pong", "reply": {"value": {"ok": True}}},
        },
    )
    coco_runner.add_endpoint(
        "avalue_check",
        {
            "group": "test",
            "values": {"ok": "bool"},
            "call": {"forward": None},
            "after": {"name": "pong", "reply": {"value": {"ok": True}}},
        },
    )
    coco_runner.add_endpoint(
        "save_to_state",
        {
            "group": "test",
            "values": {"a": "bool", "b": "bool"},
            "call": {"forward": None},
            "save_state": "fo/bar",
        },
    )
    coco_runner.add_endpoint(
        "save_to_state_fu",
        {
            "group": "test",
            "values": {"b": "bool"},
            "call": {"forward": None},
            "save_state": "fu/bar",
        },
    )
    coco_runner.add_endpoint(
        "state_check_path",
        {
            "group": "test",
            "values": {"b": "bool"},
            "call": {"forward": {"name": "pong", "reply": {"state": "fu/bar"}}},
        },
    )
    coco_runner.add_endpoint(
        "state_check_values",
        {
            "group": "test",
            "values": {"a": "bool", "b": "bool"},
            "call": {
                "forward": {
                    "name": "pong",
                    "reply": {"state": {"a": "fo/bar/a", "b": "fo/bar/b"}},
                }
            },
        },
    )

    # Test failed type check
    response = coco_runner.client(
        "-r", "FULL", "type_check_fail", "--ok=1", decode=True
    )
    for p in coco_runner.targets:
        p.assert_hit_received("/pong", {"ok": 1})

    # Check failure report
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"])
    assert len(failed_host) == N_HOSTS
    reply = response["failed_checks"]["pong"][failed_host[0]]["reply"]
    assert reply["type"] == ["ok"]

    # Test passing type check
    response = coco_runner.client("type_check", "--no-ok", decode=True)
    for p in coco_runner.targets:
        assert p.hit_count("/pong") == 2

    # Check failure report
    assert response["success"] is True
    assert "failed_checks" not in response

    # Test failed value check
    response = coco_runner.client("value_check", "--no-ok", decode=True)
    for p in coco_runner.targets:
        assert p.hit_count("/pong") == 3
    assert response["success"] is False

    response = coco_runner.client("-r", "FULL", "value_check", "--no-ok", decode=True)
    for p in coco_runner.targets:
        assert p.hit_count("/pong") == 4

    # Check failure report
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"])
    assert len(failed_host) == N_HOSTS
    reply = response["failed_checks"]["pong"][failed_host[0]]["reply"]
    assert reply["value"] == ["ok"]

    # Test passing value check
    response = coco_runner.client("value_check", "--ok", decode=True)
    for p in coco_runner.targets:
        assert p.hit_count("/pong") == 5

    # Check failure report
    assert response["success"] is True
    assert "failed_checks" not in response

    # Test failed identical check
    response = coco_runner.client(
        "-r", "FULL", "identical_check", "--rand", decode=True
    )
    for p in coco_runner.targets:
        assert p.hit_count("/rand") == 1

    # Check failure report
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["rand"].keys())
    assert len(failed_host) == N_HOSTS
    reply = response["failed_checks"]["rand"][failed_host[0]]["reply"]
    assert reply["not_identical"] == ["all"]

    # Test passing identical check
    response = coco_runner.client("identical_check", "--no-rand", decode=True)
    for p in coco_runner.targets:
        assert p.hit_count("/rand") == 2

    # Check failure report
    assert response["success"] is True
    assert "failed_checks" not in response

    # Test failed check on before
    response = coco_runner.client("-r", "FULL", "bvalue_check", "--ok", decode=True)
    for p in coco_runner.targets:
        assert p.hit_count("/pong") == 6

    # Check failure report
    assert response["success"] is False
    failed_host = list(response["pong"]["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS
    reply = response["pong"]["failed_checks"]["pong"][failed_host[0]]["reply"]
    assert reply["missing"] == ["ok"]

    # Test failed check on after
    response = coco_runner.client("-r", "FULL", "avalue_check", "--ok", decode=True)
    for p in coco_runner.targets:
        assert p.hit_count("/pong") == 7

    # Check failure report
    assert response["success"] is False
    failed_host = list(response["pong"]["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS
    reply = response["pong"]["failed_checks"]["pong"][failed_host[0]]["reply"]
    assert reply["missing"] == ["ok"]

    # Test state checks
    # -------------------------------------------------------------------
    # First without setting it (will always fail)
    response = coco_runner.client("-r", "FULL", "state_check_path", "-b", decode=True)
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS

    response = coco_runner.client(
        "-r", "FULL", "state_check_path", "--no-b", decode=True
    )
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS

    # Set the state
    response = coco_runner.client("save_to_state_fu", "--no-b", decode=True)
    assert response["success"] is True

    # Test again
    response = coco_runner.client("-r", "FULL", "state_check_path", "-b", decode=True)
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS

    response = coco_runner.client("state_check_path", "--no-b", decode=True)
    assert response["success"] is True
    assert "failed_checks" not in response

    # The same with multiple paths to compare between state and reply
    # -------------------------------------------------------------------
    # First without setting it (will always fail)
    response = coco_runner.client(
        "-r", "FULL", "state_check_values", "-a", "-b", decode=True
    )
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS

    response = coco_runner.client(
        "-r", "FULL", "state_check_values", "--no-a", "--no-b", decode=True
    )
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS

    # Set the state
    response = coco_runner.client("save_to_state", "--no-a", "--no-b", decode=True)
    assert response["success"] is True

    # Test again
    response = coco_runner.client("state_check_values", "--no-a", "--no-b", decode=True)
    assert response["success"] is True
    assert "failed_checks" not in response

    response = coco_runner.client(
        "-r", "FULL", "state_check_values", "--no-a", "-b", decode=True
    )
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS
