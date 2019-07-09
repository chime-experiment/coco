"""Test endpoint calls triggered by failures."""
import pytest

from coco.test import coco_runner
from coco.test import endpoint_farm

CONFIG = {"log_level": "INFO"}
ENDPOINTS = {
    "call_single": {
        "group": "test",
        "call": {
            "forward": {
                "name": "status",
                "reply": {"ok": {"type": "bool"}},
                "on_failure": {"call_single_host": "restart"},
            }
        },
    },
    "call_all": {
        "group": "test",
        "call": {
            "forward": {
                "name": "status",
                "reply": {"ok": {"type": "bool"}},
                "on_failure": {"call": "restart"},
            }
        },
    },
    "status": {"group": "test"},
    "restart": {"group": "test"},
}
N_CALLS = 2


def callback(data):
    """Reply with the incoming json request."""
    return data


class FailStatus(object):
    """Send an invalid reply after a fixed number of requests."""

    def __init__(self, fail_on=0):
        self.fail_on = fail_on
        self.count = 0

    def callback(self, data):
        """Return invalid reply when specified."""
        if self.count == self.fail_on:
            return {"not_ok": True}
        self.count += 1
        return {"ok": True}


N_HOSTS = 2
STATUS_FAILER = FailStatus(1)
CALLBACKS = {"restart": callback, "status": STATUS_FAILER.callback}


@pytest.fixture
def farm():
    """Create a coco runner."""
    return endpoint_farm.Farm(N_HOSTS, CALLBACKS)


@pytest.fixture
def runner(farm):
    """Create an endpoint test farm."""
    CONFIG["groups"] = {"test": farm.hosts}
    return coco_runner.Runner(CONFIG, ENDPOINTS)


def test_on_reply(farm, runner):
    """Test coco's on_failure option."""
    request = {}

    # Test call on failure
    response = runner.client("call_all", request)
    for p in farm.ports:
        assert farm.counters()[p]["status"] == 1
        assert farm.counters()[p]["restart"] == 1

    # Check failure report
    failed_host = list(response["failed_checks"]["status"].keys())
    assert len(failed_host) == 1
    reply = response["failed_checks"]["status"][failed_host[0]]["reply"]
    assert reply["missing"] == ["ok"]

    # reset count
    STATUS_FAILER.count = 0

    # Test call_single_host
    response = runner.client("call_single", request)

    # Check failure report
    failed_host = list(response["failed_checks"]["status"].keys())
    assert len(failed_host) == 1
    reply = response["failed_checks"]["status"][failed_host[0]]["reply"]
    assert reply["missing"] == ["ok"]

    # Check only failed host called restart
    for p in farm.ports:
        assert farm.counters()[p]["status"] == 2
        # only second host should have failed
        if p == int(failed_host[0].strip("http://").split(":")[1]):
            assert farm.counters()[p]["restart"] == 2
        else:
            assert farm.counters()[p]["restart"] == 1
