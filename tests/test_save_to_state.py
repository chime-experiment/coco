"""Test endpoint config option `save_state` and `get_state`."""

import pytest


@pytest.fixture
def runner(coco_runner):
    """Create a coco runner with some endpoints."""

    coco_runner.add_endpoint(
        "save",
        {
            "call": {"forward": None},
            "save_state": ["test_state/1", "test_state/2"],
            "values": {"val": "int"},
        },
    )
    coco_runner.add_endpoint(
        "get1", {"call": {"forward": None}, "get_state": "test_state/1"}
    )
    coco_runner.add_endpoint(
        "get2", {"call": {"forward": None}, "get_state": "test_state/2"}
    )

    return coco_runner


def test_save_state(runner):
    """Test get/save_state."""
    # State starts off empty

    response = runner.client("get1", decode=True)
    assert "state" in response
    assert "test_state" in response["state"]
    assert "1" in response["state"]["test_state"]
    assert response["state"]["test_state"]["1"] == {}
    response = runner.client("get2", decode=True)
    assert "state" in response
    assert "test_state" in response["state"]
    assert "2" in response["state"]["test_state"]
    assert response["state"]["test_state"]["2"] == {}

    runner.client("save", "--val=5")
    response = runner.client("get1", decode=True)
    assert "state" in response
    assert "test_state" in response["state"]
    assert "1" in response["state"]["test_state"]
    assert response["state"]["test_state"]["1"] == {"val": 5}
    response = runner.client("get2", decode=True)
    assert "state" in response
    assert "test_state" in response["state"]
    assert "2" in response["state"]["test_state"]
    assert response["state"]["test_state"]["2"] == {"val": 5}


def test_no_reset(runner):
    """Check state with it initially set."""
    runner.set_state({"test_state": {"1": {"val": 5}, "2": {"val": 5}}})
    response = runner.client("get1", decode=True)
    assert "state" in response
    assert "test_state" in response["state"]
    assert "1" in response["state"]["test_state"]
    assert response["state"]["test_state"]["1"] == {"val": 5}
    response = runner.client("get2", decode=True)
    assert "state" in response
    assert "test_state" in response["state"]
    assert "2" in response["state"]["test_state"]
    assert response["state"]["test_state"]["2"] == {"val": 5}


def test_reset(runner):
    response = runner.client("get1", decode=True)
    assert "state" in response
    assert "test_state" in response["state"]
    assert "1" in response["state"]["test_state"]
    assert response["state"]["test_state"]["1"] == {}
    response = runner.client("get2", decode=True)
    assert "state" in response
    assert "test_state" in response["state"]
    assert "2" in response["state"]["test_state"]
    assert response["state"]["test_state"]["2"] == {}
