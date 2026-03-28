import tempfile
from copy import deepcopy
from textwrap import dedent

from coco import state


def test_exclude():
    state_path = tempfile.TemporaryDirectory()
    test_state = state.State(
        "DEBUG",
        state_path.name,
        default_state_files={},
        exclude_from_reset=["foo", "bar/foo"],
    )

    dict_ = {"foo": 1, "bar": 0}
    print(f"testing bar and {dict_}")
    ex = deepcopy(dict_)
    test_state._exclude_paths("bar", ex)
    assert ex == {"bar": 0}

    print(f"testing '' and {dict_}")
    test_state._exclude_paths("", ex)
    assert ex == {"bar": 0}

    dict_ = {"bar": {"foo": 0}, "foo": 1, "fubar": 1}
    ex = deepcopy(dict_)
    print(f"testing bar and {dict_}")
    test_state._exclude_paths("bar", ex)
    assert ex == {"bar": {"foo": 0}, "fubar": 1}

    dict_ = {"bar": {"foo": 0}, "foo": 1, "fubar": 1}
    ex = deepcopy(dict_)
    print(f"testing '' and {dict_}")
    test_state._exclude_paths("", ex)
    assert ex == {"bar": {}, "fubar": 1}


def test_jinja(tmpdir):
    """Test that .j2 files are parsed properly."""

    state_path = tmpdir
    test_state = state.State(
        "DEBUG",
        str(state_path),
        default_state_files={},
        exclude_from_reset=["foo", "bar/foo"],
    )

    jinja_code = dedent("""
        {%- for id in range(16) %}
                gpu_input_buffer_{{ id }}:
                    kotekan_buffer: standard
        {%- endfor %}
        """)

    with open(tmpdir / "testfile.j2", "w") as ofile:
        ofile.write(jinja_code)

    test_state.read_from_file("res", tmpdir / "testfile.j2")

    read = test_state._storage.state["res"]
    assert len(read.keys()) == 16
