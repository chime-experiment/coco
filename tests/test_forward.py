"""Test basic endpoint call forwarding."""
import pytest
import requests

from coco.test import coco_runner
from coco.test import endpoint_farm

ENDPT_NAME = "test"
PORT = 12055
CONFIG = {"log_level": "INFO", "port": PORT}
ENDPOINTS = {ENDPT_NAME: {"group": "test", "values": {"foo": "int", "bar": "str"}}}
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
    response = runner.client(ENDPT_NAME, ["0", "1337"])

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
        runner.client(ENDPT_NAME, ["0", "1337"])
    for p in farm.ports:
        assert farm.counters()[p][ENDPT_NAME] == N_CALLS + 1


def test_wrong_vars(farm, runner):
    request = {"foo": "dfg", "bar": 1337}
    response = requests.get(f"http://localhost:{PORT}/{ENDPT_NAME}", json=request)
    assert response.status_code == 400

    request = {"foo": 1337}
    response = requests.get(f"http://localhost:{PORT}/{ENDPT_NAME}", json=request)
    assert response.status_code == 400


def test_url_args(farm, runner):
    """Test if URL arguments get forwarded to an external endpoint."""
    request = {"foo": 0, "bar": "1337"}
    request_full = request.copy()
    request_full.update({"coco_report_type": "FULL"})
    params = {"cat": "1", "hat": "rat"}
    query_str = "&".join([f"{k}={params[k]}" for k in params])

    response = requests.get(
        f"http://localhost:{PORT}/{ENDPT_NAME}?{query_str}", json=request_full
    )
    assert response.status_code == 200
    response = response.json()

    print(response)

    assert ENDPT_NAME in response
    for h in farm.hosts:
        assert h in response[ENDPT_NAME]
        assert "status" in response[ENDPT_NAME][h]
        assert "reply" in response[ENDPT_NAME][h]
        assert "params" in response[ENDPT_NAME][h]["reply"]

        request.update({"params": params})
        assert response[ENDPT_NAME][h]["status"] == 200
        assert response[ENDPT_NAME][h]["reply"] == request
