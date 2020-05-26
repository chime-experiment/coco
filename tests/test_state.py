from coco import state

from copy import deepcopy
import tempfile


def test_exclude():
    state_path = tempfile.TemporaryDirectory()
    test_state = state.State(
        "DEBUG",
        state_path.name,
        default_state_files={},
        exclude_from_reset=["foo", "bar/foo"],
    )

    dict_ = {"foo": 1, "bar": 0}
    print("testing bar and {}".format(dict_))
    ex = deepcopy(dict_)
    test_state._exclude_paths("bar", ex)
    assert ex == {"bar": 0}

    print("testing '' and {}".format(dict_))
    test_state._exclude_paths("", ex)
    assert ex == {"bar": 0}

    dict_ = {"bar": {"foo": 0}, "foo": 1, "fubar": 1}
    ex = deepcopy(dict_)
    print("testing bar and {}".format(dict_))
    test_state._exclude_paths("bar", ex)
    assert ex == {"bar": {"foo": 0}, "fubar": 1}

    dict_ = {"bar": {"foo": 0}, "foo": 1, "fubar": 1}
    ex = deepcopy(dict_)
    print("testing '' and {}".format(dict_))
    test_state._exclude_paths("", ex)
    assert ex == {"bar": {}, "fubar": 1}
