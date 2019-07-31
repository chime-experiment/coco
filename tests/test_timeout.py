"""Test basic endpoint call forwarding with timeout."""
import pytest
import time

from coco.test import coco_runner
from coco.test import endpoint_farm

ENDPT_NAME = "test"
PORT = 12055
CONFIG = {"log_level": "INFO", "port": PORT, "timeout": "1s"}
ENDPOINTS = {ENDPT_NAME: {"group": "test", "values": {"foo": "int", "bar": "str"}}}
N_CALLS = 2


def callback(data):
    """Reply with the incoming json request."""
    time.sleep(2)
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


def test_timeout_1s(farm, runner):
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

        assert response[ENDPT_NAME][h]["status"] == 0
        assert response[ENDPT_NAME][h]["reply"] == "Timeout"
