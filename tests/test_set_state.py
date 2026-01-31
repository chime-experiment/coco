"""Test endpoint config option `set_state` and `get_state`."""

import pytest

from coco.test import coco_runner, endpoint_farm
from coco.util import hash_dict

SET_ENDPT_NAME = "set"
SET_ENDPT_NAME_INT = "set_int"
SET_ENDPT_NAME_DICT = "set_dict"
GET_ENDPT_NAME = "get"
CHECK_HASH_ENDPT_NAME = "check_hash"
CHECK_HASH_ENDPT_NAME2 = "check_hash2"
CHECK_STATE_ENDPT_NAME = "check_state"
CHECK_STATE_ENDPT_NAME2 = "check_state2"
HASH_ENDPT_NAME = "hash"
EXCLUDED_STATE_PATH = "excluded/from/reset"
CONFIG = {
    "log_level": "DEBUG",
    "groups": {"no_group": ["no_host", "doesnt_exist"]},
    "exclude_from_reset": [EXCLUDED_STATE_PATH],
}
INT_VAL = 5
STATE_PATH = "test_state"
ENDPOINTS = {
    "getall": {"call": {"forward": None}, "get_state": "/"},
    SET_ENDPT_NAME: {"call": {"forward": None}, "set_state": {STATE_PATH: True}},
    SET_ENDPT_NAME_INT: {"call": {"forward": None}, "set_state": {STATE_PATH: INT_VAL}},
    SET_ENDPT_NAME_DICT: {
        "call": {"forward": None},
        "set_state": {STATE_PATH: {"s": {"n": {"a": "fu"}}}},
    },
    "set_excluded_state": {
        "call": {"forward": None},
        "set_state": {EXCLUDED_STATE_PATH: INT_VAL},
    },
    GET_ENDPT_NAME: {"call": {"forward": None}, "get_state": STATE_PATH},
    "get_excluded_state": {"call": {"forward": None}, "get_state": EXCLUDED_STATE_PATH},
    CHECK_HASH_ENDPT_NAME: {
        "group": "test",
        "values": {"data": "str"},
        "call": {
            "forward": {"name": HASH_ENDPT_NAME, "reply": {"state_hash": {"data": "/"}}}
        },
    },
    CHECK_HASH_ENDPT_NAME2: {
        "group": "test",
        "values": {"data": "str"},
        "call": {
            "forward": {
                "name": HASH_ENDPT_NAME,
                "reply": {"state_hash": {"data": "test_state/s/n"}},
            }
        },
    },
    CHECK_STATE_ENDPT_NAME: {
        "group": "test",
        "values": {"data": "str"},
        "call": {
            "forward": {
                "name": HASH_ENDPT_NAME,
                "reply": {"state": {"data": "test_state/s/n/a"}},
            }
        },
    },
    CHECK_STATE_ENDPT_NAME2: {
        "group": "test",
        "values": {"n": "dict"},
        "call": {
            "forward": {"name": HASH_ENDPT_NAME, "reply": {"state": "test_state/s/"}}
        },
    },
}


def callback(data):
    """Reply with the incoming json request."""
    return data


N_HOSTS = 1
CALLBACKS = {HASH_ENDPT_NAME: callback}


@pytest.fixture
def farm():
    """Create an endpoint test farm."""
    return endpoint_farm.Farm(N_HOSTS, CALLBACKS)


@pytest.fixture
def runner(farm):
    """Create a coco runner."""
    CONFIG["groups"] = {"test": farm.hosts}
    with coco_runner.Runner(CONFIG, ENDPOINTS) as runner:
        yield runner


def test_get_state(runner):
    """Test get/set_state."""

    # Set state to True
    runner.client(SET_ENDPT_NAME)

    # Get state and compare
    response = runner.client(GET_ENDPT_NAME)
    assert "state" in response
    assert STATE_PATH in response["state"]
    assert response["state"][STATE_PATH] is True

    # Set state to INT
    runner.client(SET_ENDPT_NAME_INT)

    # Get state and compare
    response = runner.client(GET_ENDPT_NAME)
    assert "state" in response
    assert STATE_PATH in response["state"]
    assert response["state"][STATE_PATH] == 5

    # Test passing check against state hash
    runner.client(CHECK_HASH_ENDPT_NAME, [str(hash_dict({"test_state": 5}))])
    assert "failed_checks" not in response

    # Test failing check against state hash
    response = runner.client(CHECK_HASH_ENDPT_NAME, [str(hash_dict({"foo": 5}))])
    assert "failed_checks" in response
    assert HASH_ENDPT_NAME in response["failed_checks"]
    for r in response["failed_checks"][HASH_ENDPT_NAME].values():
        assert r == {"reply": {"mismatch_with_state_hash": ["data"]}}

    response = runner.client(CHECK_HASH_ENDPT_NAME, [str(hash_dict({"test_state": 4}))])
    assert "failed_checks" in response
    assert HASH_ENDPT_NAME in response["failed_checks"]
    for r in response["failed_checks"][HASH_ENDPT_NAME].values():
        assert r == {"reply": {"mismatch_with_state_hash": ["data"]}}

    # The same for a part of the state:
    runner.client(SET_ENDPT_NAME_DICT)
    # Test passing check against partly state hash
    response = runner.client(CHECK_HASH_ENDPT_NAME2, [str(hash_dict({"a": "fu"}))])
    assert "failed_checks" not in response

    # Test failing check against partly state hash
    response = runner.client(CHECK_HASH_ENDPT_NAME2, [str(hash_dict({"a": "foo"}))])
    assert "failed_checks" in response
    assert HASH_ENDPT_NAME in response["failed_checks"]
    for r in response["failed_checks"][HASH_ENDPT_NAME].values():
        assert r == {"reply": {"mismatch_with_state_hash": ["data"]}}

    # Test checks against state
    # Test passing check against part of state
    response = runner.client(CHECK_STATE_ENDPT_NAME, ["fu"])
    assert "failed_checks" not in response

    # Test failing check against part of state
    response = runner.client(CHECK_STATE_ENDPT_NAME, ["f00"])
    assert "failed_checks" in response
    assert HASH_ENDPT_NAME in response["failed_checks"]
    for r in response["failed_checks"][HASH_ENDPT_NAME].values():
        assert r == {"reply": {"mismatch_with_state": ["data"]}}
    response = runner.client(CHECK_STATE_ENDPT_NAME, [""])
    assert "failed_checks" in response
    assert HASH_ENDPT_NAME in response["failed_checks"]
    for r in response["failed_checks"][HASH_ENDPT_NAME].values():
        assert r == {"reply": {"mismatch_with_state": ["data"]}}

    # Test passing check against state
    response = runner.client(CHECK_STATE_ENDPT_NAME2, ['{"a": "fu"}'])
    assert "failed_checks" not in response

    # Test failing check against state
    response = runner.client(CHECK_STATE_ENDPT_NAME2, ['{"n": {"a": 0}}'])
    assert "failed_checks" in response
    assert HASH_ENDPT_NAME in response["failed_checks"]
    for r in response["failed_checks"][HASH_ENDPT_NAME].values():
        assert r == {"reply": {"mismatch_with_state": ["all"]}}
    response = runner.client(CHECK_STATE_ENDPT_NAME2, ['{"aa": "fu"}'])
    assert "failed_checks" in response
    assert HASH_ENDPT_NAME in response["failed_checks"]
    for r in response["failed_checks"][HASH_ENDPT_NAME].values():
        assert r == {"reply": {"mismatch_with_state": ["all"]}}
    response = runner.client(CHECK_STATE_ENDPT_NAME2, ["{}"])
    assert "failed_checks" in response
    assert HASH_ENDPT_NAME in response["failed_checks"]
    for r in response["failed_checks"][HASH_ENDPT_NAME].values():
        assert r == {"reply": {"mismatch_with_state": ["all"]}}


def test_reset_state(runner):
    runner.client(SET_ENDPT_NAME_INT)
    response = runner.client(GET_ENDPT_NAME)
    assert "state" in response
    assert STATE_PATH in response["state"]
    assert response["state"][STATE_PATH] == INT_VAL

    runner.client("set_excluded_state")
    response = runner.client("get_excluded_state")
    assert "state" in response
    path = EXCLUDED_STATE_PATH.split("/")
    r = response["state"]
    for p in path:
        assert p in r
        r = r[p]
    assert r == INT_VAL

    runner.client("reset-state")
    response = runner.client(GET_ENDPT_NAME)
    assert "status_code" in response
    assert response["status_code"] == 500  # path not found

    response = runner.client("get_excluded_state")
    assert "state" in response
    path = EXCLUDED_STATE_PATH.split("/")
    r = response["state"]
    for p in path:
        assert p in r
        r = r[p]
    assert r == INT_VAL
