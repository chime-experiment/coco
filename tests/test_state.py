"""Tests for coco.state."""

import asyncio
import json
import pathlib

import pytest

from coco import exceptions, util
from coco.state import ACTIVE, State


def test_new_state(default_paths):
    """Test loading the state ex nihilo."""

    state = State(default_paths["storage_path"], {}, [])

    # State is empty
    assert state.is_empty()


def test_restore_active(fs, default_paths):
    """Check restoring the active state."""

    # Current state
    storage_path = default_paths["storage_path"]
    fs.create_file(f"{storage_path}/active", contents='{"active": "canary"}')

    # Instantiate the state
    state = State(default_paths["storage_path"], {}, [])

    # Verify
    assert state.read("active") == "canary"


def test_out_of_tree_state(fs, default_paths):
    """Check directory scoping.

    cocod shouldn't be reading or writing state files outside of "storage_path".
    """

    # Current state
    storage_path = default_paths["storage_path"]
    fs.create_file(f"{storage_path}/active", contents='{"active": "canary"}')

    # Create an out-of-tree state file
    elsewhere = pathlib.Path(storage_path, "../elsewhere").resolve()
    fs.create_dir(elsewhere)
    fs.create_file("{elsewhere}/state", contents='{"dont": "overwrite"}')

    # Instantiate the state
    state = State(default_paths["storage_path"], {}, [])

    # Verify
    assert state.read("active") == "canary"

    # Loading state from elsewhere shouldn't work.
    with pytest.raises(exceptions.InvalidUsage):
        asyncio.run(state.load_state({"name": "../elsewhere/state"}))

    # State hasn't changed
    assert state.read("/active") == "canary"
    assert not state.exists("dont")

    # Saving state from elesewhere shouldn't work either.
    with pytest.raises(exceptions.InvalidUsage):
        asyncio.run(state.save_state({"name": "../elsewhere/state"}))

    # File on disk not changed
    with open("{elsewhere}/state") as f:
        diskstate = json.load(f)
    assert diskstate == {"dont": "overwrite"}


def test_save_states_list(fs, default_paths):
    """Test listing saved states"""

    storage_path = default_paths["storage_path"]

    # The saved states we have
    states = {"state1", "state2", "state3", "state4"}

    # Create some (empty) saved states
    for s in states:
        fs.create_file(f"{storage_path}/{s}", contents="{}")

    # Also create the active state
    fs.create_file(f"{storage_path}/{ACTIVE}", contents="{}")

    state = State(default_paths["storage_path"], {}, [])

    # The active state isn't in the set
    assert ACTIVE not in state._saved_states

    # Check the whole set
    assert states == state._saved_states


def test_get_saved_states(fs, default_paths):
    """Test the Result from State.get_saved_states."""

    # Create some (empty) saved states
    storage_path = default_paths["storage_path"]
    states = {"state1", "state2", "state3", "state4"}
    for s in states:
        fs.create_file(f"{storage_path}/{s}")

    state = State(default_paths["storage_path"], {}, [])

    result = asyncio.run(state.get_saved_states())

    assert result.results == {"saved-states": {util.Host("coco"): sorted(states)}}
