"""Tests for coco.state."""

import asyncio
import json
import pathlib

import pytest

from coco import exceptions
from coco.state import State


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
