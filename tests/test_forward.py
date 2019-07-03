"""Test basic endpoint call forwarding."""
import pytest

from coco.test import coco_runner
from coco.test import endpoint_farm

ENDPT_NAME = "test"
CONFIG = {"log_level": "INFO"}
ENDPOINTS = {ENDPT_NAME: {"group": "test", "values": {"foo": "int", "bar": "str"}}}
N_CALLS = 2


def callback(data):
    """Reply with the incoming json request."""
    return data


N_HOSTS = 2
CALLBACKS = {ENDPT_NAME: callback}


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
    """Test if a request gets forwarded to an external endpoint."""
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

    for i in range(N_CALLS):
        runner.client(ENDPT_NAME, request)
    for p in farm.ports:
        assert farm.counters()[p][ENDPT_NAME] == N_CALLS + 1
