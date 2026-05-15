"""Tests for coco.state."""

import asyncio
import json
import os
import pathlib

import pytest

from coco import exceptions, util
from coco.state import ACTIVE, State


def test_new_state(storage_path):
    """Test loading the state ex nihilo."""

    state = State(storage_path, {}, [], False)

    # State is empty
    assert state.is_empty()


def test_restore_active(fs, storage_path):
    """Check restoring the active state."""

    # Current state
    fs.create_file(f"{storage_path}/active", contents='{"active": "canary"}')

    # Instantiate the state
    state = State(storage_path, {}, [], False)

    # Verify
    assert state.read("active") == "canary"


def test_out_of_tree_state(fs, storage_path):
    """Check directory scoping.

    cocod shouldn't be reading or writing state files outside of "storage_path".
    """

    # Current state
    fs.create_file(f"{storage_path}/active", contents='{"active": "canary"}')

    # Create an out-of-tree state file
    elsewhere = pathlib.Path(storage_path, "../elsewhere").resolve()
    fs.create_dir(elsewhere)
    fs.create_file("{elsewhere}/state", contents='{"dont": "overwrite"}')

    # Instantiate the state
    state = State(storage_path, {}, [], False)

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


def test_save_states_list(fs, storage_path):
    """Test listing saved states"""

    # The saved states we have
    states = {"state1", "state2", "state3", "state4"}

    # Create some (empty) saved states
    for s in states:
        fs.create_file(f"{storage_path}/{s}", contents="{}")

    # Also create the active state
    fs.create_file(f"{storage_path}/{ACTIVE}", contents="{}")

    state = State(storage_path, {}, [], False)

    # The active state isn't in the set
    assert ACTIVE not in state._saved_states

    # Check the whole set
    assert states == state._saved_states


def test_get_saved_states(fs, storage_path):
    """Test the Result from State.get_saved_states."""

    # Create some (empty) saved states
    states = {"state1", "state2", "state3", "state4"}
    for s in states:
        fs.create_file(f"{storage_path}/{s}")

    state = State(storage_path, {}, [], False)

    result = asyncio.run(state.get_saved_states())

    assert result.results == {"saved-states": {util.Host("coco"): sorted(states)}}


def test_save_state(fs, storage_path):
    """Test saving state."""

    # Initial state
    fs.create_file(f"{storage_path}/{ACTIVE}", contents='{"key": "value"}')

    state = State(storage_path, {}, [], False)

    # Save the state
    result = asyncio.run(state.save_state({"name": "test"}))

    assert result.results == {"save-state": {util.Host("coco"): "Saved state test"}}

    # Check file on disk
    with open(f"{storage_path}/test") as f:
        assert json.load(f) == {"key": "value"}

    # The new backup is now in the saved state list
    result = asyncio.run(state.get_saved_states())
    assert result.results == {"saved-states": {util.Host("coco"): ["test"]}}


def test_save_to_active(fs, storage_path):
    """Not allowed to save state with the name "active"."""

    # Initial state
    fs.create_file(f"{storage_path}/{ACTIVE}", contents='{"key": "value"}')

    state = State(storage_path, {}, [], False)

    # This shouldn't work.
    with pytest.raises(exceptions.InvalidUsage):
        asyncio.run(state.save_state({"name": ACTIVE}))


def test_save_to_existing(fs, storage_path):
    """Attempt to save to an existing state file."""

    # Initial state
    fs.create_file(f"{storage_path}/{ACTIVE}", contents='{"key": "value"}')

    # An old state that we want to save to
    fs.create_file(f"{storage_path}/backup", contents='{"old": "data"}')

    state = State(storage_path, {}, [], False)

    # This shouldn't work.
    with pytest.raises(exceptions.InvalidUsage):
        asyncio.run(state.save_state({"name": "backup"}))

    # But this should
    result = asyncio.run(state.save_state({"name": "backup", "overwrite": True}))

    assert result.results == {"save-state": {util.Host("coco"): "Saved state backup"}}

    # Check file on disk
    with open(f"{storage_path}/backup") as f:
        assert json.load(f) == {"key": "value"}


def test_save_overwrite_invalid(fs, storage_path):
    """Attempt to save over a currently invalid state."""

    # Initial state
    fs.create_file(f"{storage_path}/{ACTIVE}", contents='{"key": "value"}')

    # An old invalid state that we want to overwrite
    fs.create_file(f"{storage_path}/backup", contents="{{{{{{{")

    state = State(storage_path, {}, [], False)

    # This should work, even though the state currently can't be read.
    result = asyncio.run(state.save_state({"name": "backup", "overwrite": True}))

    assert result.results == {"save-state": {util.Host("coco"): "Saved state backup"}}

    # Check file on disk
    with open(f"{storage_path}/backup") as f:
        assert json.load(f) == {"key": "value"}


def test_save_state_error(fs, storage_path):
    """Test error propagation when saving state."""

    # Initial state
    fs.create_file(f"{storage_path}/{ACTIVE}", contents='{"key": "value"}')

    # Make the state directory read-only
    os.chmod(storage_path, mode=0o0500)

    state = State(storage_path, {}, [], False)

    # This shouldn't work.
    with pytest.raises(exceptions.InternalError):
        asyncio.run(state.save_state({"name": "backup"}))

    # Saved state doesn't exist
    assert not pathlib.Path(storage_path, "test").exists()


def test_state_reload(fs, storage_path):
    """Attempt to load a saved state."""

    # Current state
    fs.create_file(f"{storage_path}/active", contents='{"key": "value"}')

    # State to load
    fs.create_file(f"{storage_path}/test", contents='{"other": "data"}')

    state = State(storage_path, {}, [], False)

    # Load the other state
    result = asyncio.run(state.load_state({"name": "test"}))
    assert result.results == {"load-state": {util.Host("coco"): "Loaded state test"}}

    # Check that it's now the active state.
    assert state.read("other") == "data"


def test_state_reload_error(fs, storage_path):
    """Test errors in load-state."""

    # Current state
    fs.create_file(f"{storage_path}/active", contents='{"key": "value"}')

    # States to load
    fs.create_file(f"{storage_path}/invalid", contents="{{{{{")
    fs.create_file(f"{storage_path}/missing", contents="{}")

    state = State(storage_path, {}, [], False)

    # Loading invalid state fails
    with pytest.raises(exceptions.InternalError):
        asyncio.run(state.load_state({"name": "invalid"}))

    # State hasn't changed
    assert state.read("key") == "value"

    # Loading missing state fails
    os.unlink(f"{storage_path}/missing")
    with pytest.raises(exceptions.InternalError):
        asyncio.run(state.load_state({"name": "missing"}))

    # State hasn't changed
    assert state.read("key") == "value"


def test_reset_state(fs, storage_path):
    """Check resetting the state."""

    # Current state
    fs.create_file(
        f"{storage_path}/active", contents='{"keep": "keep", "discard": "discard"}'
    )

    # Default state file
    fs.create_file("/coco/default.yaml", contents="key: value")

    # Instantiate the state.  "keep" is in the exclude_from_reset list.
    state = State(storage_path, {"loaded": "/coco/default.yaml"}, ["keep"], False)

    # Verify state was restored
    assert state.read("keep") == "keep"
    assert state.read("discard") == "discard"

    # Reset state
    asyncio.run(state.reset_state())

    # "keep" has been kept, but "discard" is discarded
    assert state.read("keep") == "keep"
    assert not state.exists("discard")

    # Conf has been loaded from disk
    assert state.read("loaded/key") == "value"


def test_reset_on_init(fs, storage_path):
    """Check reset-on-init / full-reset."""

    # Current state
    fs.create_file(
        f"{storage_path}/active", contents='{"keep": "keep", "discard": "discard"}'
    )

    # Instantiate the state.  "keep" is in the exclude_from_reset list.
    state = State(storage_path, {}, ["keep"], True)

    # State is empty (exclude_from_reset was ignored).
    assert state.is_empty()
