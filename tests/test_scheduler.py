"""Test endpoint scheduler."""
import pytest
import time
import tempfile
import json

from coco.test import coco_runner
from coco.test import endpoint_farm

CONFIG = {"log_level": "DEBUG"}
STATE_PATH = "test/success"
STATE_PATH_FAIL_TYPE = "test/fail_type"
STATE_PATH_FAIL_VAL = "test/fail_val"
PERIOD = 1.5
ENDPOINTS = {
    "scheduled": {"group": "test", "schedule": {"period": PERIOD}},
    "scheduled-check-type": {
        "group": "test",
        "schedule": {
            "period": PERIOD,
            "require_state": {"path": STATE_PATH, "type": "bool"},
        },
    },
    "scheduled-check-val": {
        "group": "test",
        "schedule": {
            "period": PERIOD,
            "require_state": {"path": STATE_PATH, "type": "bool", "value": True},
        },
    },
    "scheduled-fail-type": {
        "group": "test",
        "schedule": {
            "period": PERIOD,
            "require_state": {"path": STATE_PATH_FAIL_TYPE, "type": "bool"},
        },
    },
    "scheduled-fail-val": {
        "group": "test",
        "schedule": {
            "period": PERIOD,
            "require_state": {
                "path": STATE_PATH_FAIL_VAL,
                "type": "bool",
                "value": True,
            },
        },
    },
}


def callback(data):
    """Reply with the incoming json request."""
    return data


CALLBACKS = {endpt: callback for endpt in ENDPOINTS}
STATEFILE = tempfile.NamedTemporaryFile("w")
N_HOSTS = 2


@pytest.fixture
def farm():
    """Create an endpoint test farm."""
    return endpoint_farm.Farm(N_HOSTS, CALLBACKS)


@pytest.fixture
def runner(farm):
    """Create a coco runner."""
    CONFIG["groups"] = {"test": farm.hosts}
    state = {
        STATE_PATH.split("/")[1]: True,
        STATE_PATH_FAIL_TYPE.split("/")[1]: "not_a_bool",
        STATE_PATH_FAIL_VAL.split("/")[1]: False,
    }
    json.dump(state, STATEFILE)
    STATEFILE.flush()
    CONFIG["load_state"] = {STATE_PATH.split("/")[0]: STATEFILE.name}
    print(STATEFILE.name)
    return coco_runner.Runner(CONFIG, ENDPOINTS)


def test_sched(farm, runner):
    """Test if scheduled endpoints are called when they should be."""
    start_t = time.time()
    # Let three periods pass
    time.sleep(3 * PERIOD + 0.5)

    counters = farm.counters()
    end_t = time.time()

    num_sched = (end_t - start_t) // PERIOD

    for p in farm.ports:
        assert counters[p]["scheduled"] == num_sched
        assert counters[p]["scheduled-check-type"] == num_sched
        assert counters[p]["scheduled-check-val"] == num_sched
        assert "scheduled-fail-type" not in counters[p]
        assert "scheduled-fail-val" not in counters[p]

    runner.stop_coco()
