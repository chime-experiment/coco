"""Test conditions on endpoint call forwarding."""
import pytest
import requests

from coco.test import coco_runner
from coco.test import endpoint_farm

ENDPT_NAME = "test"
ENDPT_NAME_SET = "feelgood"
PORT = 12055
CONFIG = {"log_level": "INFO", "port": PORT}
ENDPOINTS = {
    ENDPT_NAME: {
        "group": "test",
        "values": {"foo": "int", "bar": "str"},
        "require_state": {"path": "feeling/good", "type": "bool", "value": True},
    },
    ENDPT_NAME_SET: {
        "group": "test",
        "values": {"good": "bool"},
        "save_state": "feeling",
        "call": {"forward": None},
    },
}
N_CALLS = 2


def callback(data):
    """Reply with the incoming json request."""
    return data


N_HOSTS = 2
CALLBACKS = {ENDPT_NAME: callback}


@pytest.fixture(scope="module")
def farm():
    """Create a coco runner."""
    return endpoint_farm.Farm(N_HOSTS, CALLBACKS)


@pytest.fixture(scope="module")
def runner(farm):
    """Create an endpoint test farm."""
    CONFIG["groups"] = {"test": farm.hosts}
    return coco_runner.Runner(CONFIG, ENDPOINTS)


def test_forward(farm, runner):
    """Test if a request gets forwarded to an external endpoint."""
    request = {"foo": 0, "bar": "1337"}
    response = runner.client(ENDPT_NAME, request)

    for p in farm.ports:
        assert not hasattr(farm.counters()[p], ENDPT_NAME)
    assert response["status_code"] == 409

    # Change the state to meet the condition
    request = {"good": True}
    response = runner.client(ENDPT_NAME_SET, request)
    assert response["success"]

    # Now it should go through...
    request = {"foo": 0, "bar": "1337"}
    response = runner.client(ENDPT_NAME, request)

    for p in farm.ports:
        assert farm.counters()[p][ENDPT_NAME] == 1
    assert ENDPT_NAME in response
    for h in farm.hosts:
        assert h in response[ENDPT_NAME]
        assert "status" in response[ENDPT_NAME][h]
        assert "reply" in response[ENDPT_NAME][h]

        assert response[ENDPT_NAME][h]["status"] == 200
        assert response[ENDPT_NAME][h]["reply"] == request

    # Turn it off again
    request = {"good": False}
    response = runner.client(ENDPT_NAME_SET, request)
    assert response["success"]

    # Now it should be disabled again
    request = {"foo": 0, "bar": "1337"}
    response = runner.client(ENDPT_NAME, request)

    for p in farm.ports:
        assert farm.counters()[p][ENDPT_NAME] == 1
    assert response["status_code"] == 409
