"""Tests for coco.state."""

from coco.state import State


def test_new_state(default_paths):
    """Test loading the state ex nihilo."""

    state = State(default_paths["storage_path"], {}, [])

    # State is empty
    assert state.is_empty()
