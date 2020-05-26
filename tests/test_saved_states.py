"""Test saving and loading states."""

import json
import pathlib
import pytest
import tempfile

from coco.test import coco_runner

SAVE_ENDPT_NAME = "save"
SAVE_EXCLUDED_ENDPT_NAME = "save_excluded"

state_dir = tempfile.TemporaryDirectory()
active_state = pathlib.Path(state_dir.name, "active")
saved_state = pathlib.Path(state_dir.name, "backup")

INT_VAL = 5
INT_VAL_NAME = "val"
STATE_PATH = "test_state"
EXCLUDED_PATH = "excluded"

CONFIG = {
    "log_level": "INFO",
    "storage_path": state_dir.name,
    "exclude_from_reset": [EXCLUDED_PATH],
    "groups": {"no_group": ["no_host", "doesnt_exist"]},
}

ENDPOINTS = {
    SAVE_ENDPT_NAME: {
        "call": {"forward": None},
        "save_state": [STATE_PATH + "/1", STATE_PATH + "/2"],
        "values": {INT_VAL_NAME: "int"},
    },
    SAVE_EXCLUDED_ENDPT_NAME: {
        "call": {"forward": None},
        "save_state": [EXCLUDED_PATH],
        "values": {INT_VAL_NAME: "int"},
    },
}


@pytest.fixture
def runner():
    return coco_runner.Runner(CONFIG, ENDPOINTS)


def test_save_state(runner):
    """Test saving the state."""
    assert saved_state.exists() is False

    # Save the state, check it exists and is identical to the active state.
    runner.client("save-state", ["backup"])
    assert saved_state.exists()
    with open(saved_state, "r") as saved, open(active_state, "r") as active:
        assert json.load(saved) == json.load(active)

    # change the active state and check that now it differs from the backup
    runner.client(SAVE_ENDPT_NAME, [str(INT_VAL)])
    with open(saved_state, "r") as saved, open(active_state, "r") as active:
        assert json.load(saved) != json.load(active)

    # load the backup as the active state again
    runner.client("load-state", ["backup"])
    with open(saved_state, "r") as saved, open(active_state, "r") as active:
        assert json.load(saved) == json.load(active)

    # Alter the excluded part of the active config. This difference should survive a load-state.
    runner.client(SAVE_EXCLUDED_ENDPT_NAME, [str(INT_VAL)])
    runner.client("load-state", ["backup"])
    with open(saved_state, "r") as saved, open(active_state, "r") as active:
        assert json.load(saved) != json.load(active)

    # try overwriting without and with setting overwrite=True
    result = runner.client("save-state", ["backup"])
    assert result["status_code"] == 400
    with open(saved_state, "r") as saved, open(active_state, "r") as active:
        assert json.load(saved) != json.load(active)

    result = runner.client("save-state", ["--overwrite", "backup"])
    assert result["success"] == True
    with open(saved_state, "r") as saved, open(active_state, "r") as active:
        assert json.load(saved) == json.load(active)

    # test the saved-states endpoint
    get_states = runner.client("saved-states")
    assert get_states["saved-states"]["http://coco/"]["reply"] == ["backup"]

    # add one more saved state and test again
    runner.client("save-state", ["blubb"])
    get_states = runner.client("saved-states")
    assert get_states["saved-states"]["http://coco/"]["reply"] == ["backup", "blubb"]

    # Try to save into active state
    result = runner.client("save-state", ["active"])
    assert result["status_code"] == 400

    # Try to load active state
    result = runner.client("load-state", ["active"])
    assert result["status_code"] == 400

    # Try to load state that doesn't exist
    result = runner.client("load-state", ["argh"])
    assert result["status_code"] == 400
