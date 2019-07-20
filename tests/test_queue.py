"""Test the limited length queue."""
import pytest
from aiohttp import request
import requests
import asyncio
from prometheus_client.parser import text_string_to_metric_families
import time

from coco.test import coco_runner
from coco.test import endpoint_farm

PORT = 12055
METRIC_PORT = 12056
T_WAIT = 2
QUEUE_LEN = 3
CONFIG = {
    "log_level": "DEBUG",
    "queue_length": QUEUE_LEN,
    "port": PORT,
    "metrics_port": METRIC_PORT,
}
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


async def _client(config, endpoint, sleep=None):
    if sleep:
        await asyncio.sleep(sleep)
    async with request(
        "get", f"http://localhost:{PORT}/{endpoint}", json={"coco_report_type": "FULL"}
    ) as r:
        return await r.json()


def test_queue(farm, runner):
    """Test queue limit."""
    # Wait for coco to start up
    time.sleep(1)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Set up client tasks
    wait = _client(runner.configfile.name, "do_wait")
    clients = []
    for i in range(QUEUE_LEN + 1):
        clients.append(_client(runner.configfile.name, "test", sleep=0.1))
    # Send requests
    replies = loop.run_until_complete(asyncio.gather(wait, *clients))
    loop.close()

    # Check responses
    failed = 0
    for r in replies[1:]:
        if "status" in r:
            assert r["status"] == 503
            failed += 1
        else:
            for h in farm.hosts:
                assert h in r["test"]
                assert r["test"][h]["status"] == 200
    # Not certain they came in order, but only one should have been dropped
    assert failed == 1

    # Check metrics record dropped requests
    metrics = requests.get(f"http://localhost:{METRIC_PORT}/metrics")
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
