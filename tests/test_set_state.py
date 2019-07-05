"""Test endpoint config option `set_state` and `get_state`."""
import pytest

from coco.test import coco_runner

SET_ENDPT_NAME = "set"
SET_ENDPT_NAME_INT = "set_int"
GET_ENDPT_NAME = "get"
CONFIG = {"log_level": "INFO", "groups": {"no_group": ["no_host", "doesnt_exist"]}}
INT_VAL = 5
STATE_PATH = "test_state"
ENDPOINTS = {
    SET_ENDPT_NAME: {"call": {"forward": None}, "set_state": {STATE_PATH: True}},
    SET_ENDPT_NAME_INT: {"call": {"forward": None}, "set_state": {STATE_PATH: INT_VAL}},
    GET_ENDPT_NAME: {"call": {"forward": None}, "get_state": STATE_PATH},
}


@pytest.fixture
def runner():
    """Create a coco runner."""
    return coco_runner.Runner(CONFIG, ENDPOINTS)


def test_get_state(runner):
    """Test get/set_state."""
    # State should be empty now
    response = runner.client(GET_ENDPT_NAME)
    assert "state" in response
    assert STATE_PATH in response["state"]
    assert response["state"][STATE_PATH] == {}

    # Set state to True
    runner.client(SET_ENDPT_NAME)
    response = runner.client(GET_ENDPT_NAME)
    assert "state" in response
    assert STATE_PATH in response["state"]
    assert response["state"][STATE_PATH] is True

    # Set state to INT
    runner.client(SET_ENDPT_NAME_INT)
    response = runner.client(GET_ENDPT_NAME)
    assert "state" in response
    assert STATE_PATH in response["state"]
    assert response["state"][STATE_PATH] == 5
