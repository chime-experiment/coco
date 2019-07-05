"""Test call forwarding to other coco endpoints."""
import pytest

from coco.test import coco_runner
from coco.test import endpoint_farm

ENDPT_NAME = "proxy"
ENDPT_NAME2 = "end"
CONFIG = {"log_level": "INFO"}
ENDPOINTS = {
    ENDPT_NAME: {
        "call": {"coco": ENDPT_NAME2},
        "group": "test",
        "values": {"foo": "int", "bar": "str"},
    },
    ENDPT_NAME2: {"group": "test", "values": {"foo": "int", "bar": "str"}},
}
N_CALLS = 2


def callback(data):
    """Reply with the incoming json request."""
    return data


N_HOSTS = 2
CALLBACKS = {"end": callback}


@pytest.fixture
def farm():
    """Create a coco runner."""
    return endpoint_farm.Farm(N_HOSTS, CALLBACKS)


@pytest.fixture
def runner(farm):
    """Create an endpoint test farm."""
    CONFIG["groups"] = {"test": farm.hosts}
    return coco_runner.Runner(CONFIG, ENDPOINTS)


def test_forward(farm, runner):
    """Test if a request gets forwarded to another coco endpoint."""
    request = {"foo": 0, "bar": "1337"}
    response = runner.client(ENDPT_NAME, request)

    for p in farm.ports:
        assert farm.counters()[p][ENDPT_NAME] == 1
        assert farm.counters()[p][ENDPT_NAME2] == 1
    assert ENDPT_NAME in response
    assert ENDPT_NAME2 in response
    response = response[ENDPT_NAME2]
    for h in farm.hosts:
        assert h in response[ENDPT_NAME2]
        assert "status" in response[ENDPT_NAME2][h]
        assert "reply" in response[ENDPT_NAME2][h]

        assert response[ENDPT_NAME2][h]["status"] == 200
        assert response[ENDPT_NAME2][h]["reply"] == request

    for i in range(N_CALLS):
        runner.client(ENDPT_NAME, request)
    for p in farm.ports:
        assert farm.counters()[p][ENDPT_NAME] == N_CALLS + 1
        assert farm.counters()[p][ENDPT_NAME2] == N_CALLS + 1
