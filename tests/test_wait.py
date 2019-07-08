"""Test the internal WAIT endpoint."""
import pytest
import time

from coco.test import coco_runner
from coco.test import endpoint_farm

ENDPT_NAME = "test"
CONFIG = {"log_level": "INFO"}
T_WAIT = 2
T_HOW_SLOW_IS_COCO = 1
ENDPOINTS = {
    ENDPT_NAME: {
        "group": "test",
        "values": {"foo": "int", "bar": "str"},
        "call": {"coco": {"name": "wait", "request": {"seconds": T_WAIT}}},
    }
}
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
    t0 = time.time()
    response = runner.client(ENDPT_NAME, request)
    t1 = time.time()
    assert t1 - t0 > T_WAIT
    assert t1 - t0 < T_WAIT + T_HOW_SLOW_IS_COCO

    for p in farm.ports:
        assert farm.counters()[p][ENDPT_NAME] == 1
    assert ENDPT_NAME in response
    for h in farm.hosts:
        assert h in response[ENDPT_NAME]
        assert "status" in response[ENDPT_NAME][h]
        assert "reply" in response[ENDPT_NAME][h]

        assert response[ENDPT_NAME][h]["status"] == 200
        assert response[ENDPT_NAME][h]["reply"] == request
