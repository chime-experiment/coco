"""Test endpoint calls triggered by failures."""
import multiprocessing
import random

import pytest

from coco.test import coco_runner
from coco.test import endpoint_farm

CONFIG = {"log_level": "INFO"}
ENDPOINTS = {
    "type_check": {
        "group": "test",
        "values": {"ok": "bool"},
        "call": {"forward": {"name": "pong", "reply": {"type": {"ok": "bool"}}}},
    },
    "type_check_fail": {
        "group": "test",
        "values": {"ok": "int"},
        "call": {"forward": {"name": "pong", "reply": {"type": {"ok": "bool"}}}},
    },
    "value_check": {
        "group": "test",
        "values": {"ok": "bool"},
        "call": {"forward": {"name": "pong", "reply": {"value": {"ok": True}}}},
    },
    "identical_check": {
        "group": "test",
        "values": {"rand": "bool"},
        "call": {"forward": {"name": "rand", "reply": {"identical": ["rand"]}}},
    },
    "pong": {"group": "test"},
    "rand": {"group": "test"},
    # For before check
    "bvalue_check": {
        "group": "test",
        "values": {"ok": "bool"},
        "call": {"forward": None},
        "before": {"name": "pong", "reply": {"value": {"ok": True}}},
    },
    "avalue_check": {
        "group": "test",
        "values": {"ok": "bool"},
        "call": {"forward": None},
        "after": {"name": "pong", "reply": {"value": {"ok": True}}},
    },
    "save_to_state": {
        "group": "test",
        "values": {"a": "bool", "b": "bool"},
        "call": {"forward": None},
        "save_state": "fo/bar",
    },
    "save_to_state_fu": {
        "group": "test",
        "values": {"b": "bool"},
        "call": {"forward": None},
        "save_state": "fu/bar",
    },
    "state_check_path": {
        "group": "test",
        "values": {"b": "bool"},
        "call": {"forward": {"name": "pong", "reply": {"state": "fu/bar"}}},
    },
    "state_check_values": {
        "group": "test",
        "values": {"a": "bool", "b": "bool"},
        "call": {
            "forward": {
                "name": "pong",
                "reply": {"state": {"a": "fo/bar/a", "b": "fo/bar/b"}},
            }
        },
    },
}
N_CALLS = 2


def callback(data):
    """Reply with the incoming json request."""
    return data


class RandCallback(object):
    """
    Reply with a not repeating random number if rand=True received, otherwise reply with a
    fixed number.
    """

    def __init__(self):
        self.fixed_num = multiprocessing.Value("d", 0.0)

    def __call__(self, data):
        if data["rand"]:
            rand = random.random()

            with self.fixed_num.get_lock():
                self.fixed_num.value += rand
            return {"rand": rand}
        else:
            return {"rand": self.fixed_num.value}


rand_callback = RandCallback()

N_HOSTS = 2
CALLBACKS = {"pong": callback, "rand": rand_callback}


@pytest.fixture
def farm():
    """Create a coco runner."""
    return endpoint_farm.Farm(N_HOSTS, CALLBACKS)


@pytest.fixture
def runner(farm):
    """Create an endpoint test farm."""
    CONFIG["groups"] = {"test": farm.hosts}
    with coco_runner.Runner(CONFIG, ENDPOINTS) as runner:
        yield runner


def test_forward(farm, runner):
    """Test coco's forward reply check."""
    # Test failed type check
    response = runner.client("type_check_fail", ["1"])
    for p in farm.ports:
        assert farm.counters()[p]["pong"] == 1

    # Check failure report
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS
    reply = response["failed_checks"]["pong"][failed_host[0]]["reply"]
    assert reply["type"] == ["ok"]

    # Test passing type check
    response = runner.client("type_check", ["False"])
    for p in farm.ports:
        assert farm.counters()[p]["pong"] == 2

    # Check failure report
    assert response["success"] is True
    assert "failed_checks" not in response

    # Test failed value check
    response = runner.client("value_check", ["False"])
    for p in farm.ports:
        assert farm.counters()[p]["pong"] == 3
    assert response["success"] is False

    response = runner.client("value_check", ["False"])
    for p in farm.ports:
        assert farm.counters()[p]["pong"] == 4

    # Check failure report
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS
    reply = response["failed_checks"]["pong"][failed_host[0]]["reply"]
    assert reply["value"] == ["ok"]

    # Test passing value check
    response = runner.client("value_check", ["True"])
    for p in farm.ports:
        assert farm.counters()[p]["pong"] == 5

    # Check failure report
    assert response["success"] is True
    assert "failed_checks" not in response

    # Test failed identical check
    response = runner.client("identical_check", ["True"])
    for p in farm.ports:
        assert farm.counters()[p]["rand"] == 1

    # Check failure report
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["rand"].keys())
    assert len(failed_host) == N_HOSTS
    reply = response["failed_checks"]["rand"][failed_host[0]]["reply"]
    assert reply["not_identical"] == ["all"]

    # Test passing identical check
    response = runner.client("identical_check", ["False"])
    for p in farm.ports:
        assert farm.counters()[p]["rand"] == 2

    # Check failure report
    assert response["success"] is True
    assert "failed_checks" not in response

    # Test failed check on before
    response = runner.client("bvalue_check", ["True"])
    for p in farm.ports:
        assert farm.counters()[p]["pong"] == 6

    # Check failure report
    assert response["success"] is False
    failed_host = list(response["pong"]["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS
    reply = response["pong"]["failed_checks"]["pong"][failed_host[0]]["reply"]
    assert reply["missing"] == ["ok"]

    # Test failed check on after
    response = runner.client("avalue_check", ["True"])
    for p in farm.ports:
        assert farm.counters()[p]["pong"] == 7

    # Check failure report
    assert response["success"] is False
    failed_host = list(response["pong"]["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS
    reply = response["pong"]["failed_checks"]["pong"][failed_host[0]]["reply"]
    assert reply["missing"] == ["ok"]

    # Test state checks
    # -------------------------------------------------------------------
    # First without setting it (will always fail)
    response = runner.client("state_check_path", ["True"])
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS

    response = runner.client("state_check_path", ["False"])
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS

    # Set the state
    response = runner.client("save_to_state_fu", ["False"])
    assert response["success"] is True

    # Test again
    response = runner.client("state_check_path", ["True"])
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS

    response = runner.client("state_check_path", ["False"])
    assert response["success"] is True
    assert "failed_checks" not in response

    # The same with multiple paths to compare between state and reply
    # -------------------------------------------------------------------
    # First without setting it (will always fail)
    response = runner.client("state_check_values", ["True", "True"])
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS

    response = runner.client("state_check_values", ["False", "False"])
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS

    # Set the state
    response = runner.client("save_to_state", ["False", "False"])
    assert response["success"] is True

    # Test again
    response = runner.client("state_check_values", ["False", "False"])
    assert response["success"] is True
    assert "failed_checks" not in response

    response = runner.client("state_check_values", ["False", "True"])
    assert response["success"] is False
    failed_host = list(response["failed_checks"]["pong"].keys())
    assert len(failed_host) == N_HOSTS
