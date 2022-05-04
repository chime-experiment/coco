"""Test basic endpoint call forwarding with timeout."""
import pytest
import time

from coco.test import coco_runner
from coco.test import endpoint_farm

ENDPT_NAME = "test"
PORT = 12055
N_CALLS = 2
CONFIG = {
    "log_level": "INFO",
    "port": PORT,
    "timeout": "10s",
    "debug_connections": True,
}
ENDPOINTS = {
    ENDPT_NAME: {
        "call": {"forward": {"name": ENDPT_NAME, "timeout": "1s"}},
        "group": "test",
        "values": {"foo": "int", "bar": "str"},
    }
}


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
    with coco_runner.Runner(CONFIG, ENDPOINTS) as runner:
        yield runner


def test_timeout_for_specific_forward(farm, runner):
    response = runner.client(ENDPT_NAME, ["0", "1337"])

    for p in farm.ports:
        assert farm.counters()[p][ENDPT_NAME] == 1
    assert ENDPT_NAME in response
    for h in farm.hosts:
        assert h in response[ENDPT_NAME]
        assert "status" in response[ENDPT_NAME][h]
        assert "reply" in response[ENDPT_NAME][h]

        assert response[ENDPT_NAME][h]["status"] == 0
        assert response[ENDPT_NAME][h]["reply"] == "Timeout"
