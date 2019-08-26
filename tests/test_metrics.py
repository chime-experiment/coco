"""Test prometheus metrics collection."""
import pytest
import requests
from prometheus_client.parser import text_string_to_metric_families

from coco.test import coco_runner
from coco.test import endpoint_farm


PORT = 12056
CONFIG = {"log_level": "INFO", "metrics_port": PORT}
ENDPT_NAME = "status"
ENDPT_NAME_FWD = "status-host"
ENDPOINTS = {
    ENDPT_NAME: {
        "call": {"forward": ENDPT_NAME_FWD},
        "group": "test",
        "values": {"foo": "int", "bar": "str"},
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


def test_metrics(farm, runner):
    """Test metrics are counting endpoint calls."""
    request = {"foo": 0, "bar": "1337"}
    for i in range(N_CALLS):
        response = runner.client(ENDPT_NAME, request)

    # Get metrics
    metrics = requests.get(f"http://localhost:{PORT}/metrics")
    assert metrics.status_code == 200
    metrics = text_string_to_metric_families(metrics.text)

    # parse metrics
    count_coco = []
    count_forward = []
    for metric in metrics:
        for sample in metric.samples:
            if sample.name == f"coco_dropped_request_total":
                count_coco.append(sample)
            elif sample.name == f"coco_calls_total":
                count_forward.append(sample)

    # Only expect one endpoint call
    assert len(count_coco) == 5  # 1, plus two from internal metrics. Needs to be kept up to date
    count_coco = count_coco[0]
    assert list(count_coco.labels.keys()) == ["endpoint"]
    assert count_coco.labels["endpoint"] == ENDPT_NAME
    # No requests should have been dropped
    assert count_coco.value == 0

    # Expect one sample per host per endpoint
    assert len(count_forward) == N_HOSTS
    for s in count_forward:
        assert set(s.labels.keys()) == set(["endpoint", "host", "port", "status"])
    for p in farm.ports:
        ind = [int(s.labels["port"]) for s in count_forward].index(p)
        assert count_forward[ind].labels["endpoint"] == ENDPT_NAME_FWD
        assert count_forward[ind].labels["status"] == "200"
        assert count_forward[ind].labels["host"] == "localhost"
        assert count_forward[ind].value == N_CALLS
        assert farm.counters()[p][ENDPT_NAME_FWD] == N_CALLS

    del metrics
