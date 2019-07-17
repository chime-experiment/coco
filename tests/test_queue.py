"""Test the limited length queue."""
import pytest
import requests
from prometheus_client.parser import text_string_to_metric_families
from subprocess import Popen, PIPE
import time
import json

from coco.test import coco_runner
from coco.test import endpoint_farm

PORT = 12056
T_WAIT = 5
QUEUE_LEN = 3
CONFIG = {"log_level": "DEBUG", "queue_length": QUEUE_LEN}
ENDPOINTS = {
    "do_wait": {
        "group": "test",
        "call": {"coco": {"name": "wait", "request": {"seconds": T_WAIT}}},
    },
    "test": {"group": "test"},
}


def callback(data):
    """Reply with the incoming json request."""
    return data


N_HOSTS = 2
CALLBACKS = {edpt: callback for edpt in ENDPOINTS}


@pytest.fixture
def farm():
    """Create an endpoint test farm."""
    return endpoint_farm.Farm(N_HOSTS, CALLBACKS)


@pytest.fixture
def runner(farm):
    """Create a coco runner."""
    CONFIG["groups"] = {"test": farm.hosts}
    return coco_runner.Runner(CONFIG, ENDPOINTS)


def _client_process(config, endpoint):
    return Popen(coco_runner.CLIENT_ARGS + ["-c", config, endpoint], encoding="utf-8", stdout=PIPE)


def test_queue(farm, runner):
    """Test queue limit."""
    # Block on wait endpoint
    wait = _client_process(runner.configfile.name, "do_wait")
    time.sleep(1)
    # Spam with requests
    clients = []
    for i in range(QUEUE_LEN + 1):
        clients.append(_client_process(runner.configfile.name, "test"))
        # make sure these get called in order
        time.sleep(0.1)

    # Check responses
    for i, c in enumerate(clients):
        response = json.loads(c.communicate()[0])
        if i < QUEUE_LEN:
            for h in farm.hosts:
                assert h in response["test"]
                assert response["test"][h]["status"] == 200
        else:
            assert response["status"] == 503
        c.terminate()
    wait.terminate()

    # Check metrics record dropped requests
    metrics = requests.get(f"http://localhost:{PORT}/metrics")
    assert metrics.status_code == 200
    metrics = text_string_to_metric_families(metrics.text)

    # parse metrics
    count_coco = []
    for metric in metrics:
        for sample in metric.samples:
            if sample.name == f"coco_dropped_request_total":
                count_coco.append(sample)

    # Find test endpoint metric
    missing = True
    for sample in count_coco:
        if sample.labels["endpoint"] == "test":
            assert sample.value == 1.0
            missing = False
    assert not missing

    runner.stop_coco()
