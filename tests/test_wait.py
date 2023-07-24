"""Test the internal WAIT endpoint."""
import pytest
import time

from coco.test import coco_runner
from coco.test import endpoint_farm

ENDPT_NAME = "test"
TS_ENDPT_NAME = "ts_endpt"
GET_TS_ENDPT_NAME = "get_ts_endpt"
TS_PATH = "timestamps/test"
CONFIG = {"log_level": "INFO"}
T_WAIT = 2
T_HOW_SLOW_IS_COCO = 2.5
ENDPOINTS = {
    ENDPT_NAME: {
        "group": "test",
        "values": {"foo": "int", "bar": "str"},
        "call": {"coco": {"name": "wait", "request": {"duration": f"{T_WAIT}s"}}},
    },
    TS_ENDPT_NAME: {"group": "test", "timestamp": TS_PATH},
    GET_TS_ENDPT_NAME: {"group": "test", "get_state": TS_PATH},
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
    with coco_runner.Runner(CONFIG, ENDPOINTS) as runner:
        yield runner


def test_forward(farm, runner):
    """Test if a request gets forwarded to an external endpoint."""
    request = {"foo": 0, "bar": "1337"}
    t0 = time.time()
    response = runner.client(ENDPT_NAME, ["0", "1337"])
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


def test_timestamp(farm, runner):
    response = runner.client(TS_ENDPT_NAME)
    for p in farm.ports:
        assert farm.counters()[p][TS_ENDPT_NAME] == 1
    assert TS_ENDPT_NAME in response
    for h in farm.hosts:
        assert h in response[TS_ENDPT_NAME]
        assert "status" in response[TS_ENDPT_NAME][h]
        assert "reply" in response[TS_ENDPT_NAME][h]

        assert response[TS_ENDPT_NAME][h]["status"] == 200

    response = runner.client(GET_TS_ENDPT_NAME)
    for p in farm.ports:
        assert farm.counters()[p][GET_TS_ENDPT_NAME] == 1
    assert GET_TS_ENDPT_NAME in response
    assert "state" in response
    assert "timestamps" in response["state"]
    assert "test" in response["state"]["timestamps"]
    timestamp = response["state"]["timestamps"]["test"]
    assert isinstance(timestamp, float)
    # This timestamps should be fresh. Test that it's between 0 and 10s old.
    assert time.time() - timestamp > 0
    assert time.time() - timestamp < 10
