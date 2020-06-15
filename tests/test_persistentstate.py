"""Test the PersistentState."""
import json

import pytest

from coco.util import PersistentState


def test_state(tmp_path):
    """I'm only bothering to put this docstring here, because pydocstyle is super annoying."""

    # Create persistent state
    p = tmp_path / "state.json"
    ps = PersistentState(p)

    # Test the default state
    assert ps.state is None

    test_state = {"message": "Hello World!"}

    # Test that an update can be read in Python space
    with ps.update():
        ps.state = test_state

    # Check that state is set to be the same
    assert ps.state == test_state
    # ... but also that it is a copy not a reference
    assert ps.state is not test_state
    assert ps._state is not test_state

    # Test that the update is available on disk
    with p.open("r") as fh:
        disk_state = json.load(fh)
    assert disk_state == ps.state

    with pytest.raises(RuntimeError) as excinfo:
        with ps.update():
            # Update with an unserialisable type to make it fail
            ps.state = lambda x: x

    assert type(excinfo.value.__cause__) is TypeError

    # Test that the state has not changed
    assert ps.state == test_state

    # Test that the state has not changed on disk either
    with p.open("r") as fh:
        disk_state = json.load(fh)
    assert disk_state == ps.state
