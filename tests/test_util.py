"""Unit tests for coco.util."""

import json
import os
import pathlib
from datetime import timedelta

import pytest

from coco import exceptions, util


def test_str2timedelta():
    """Tests for str2timedelta."""

    assert util.str2timedelta("1234") == timedelta(seconds=1234)
    assert util.str2timedelta("567s") == timedelta(seconds=567)
    assert util.str2timedelta("9m") == timedelta(seconds=9 * 60)
    assert util.str2timedelta("1h30m") == timedelta(seconds=90 * 60)
    assert util.str2timedelta("1h12s") == timedelta(seconds=3612)

    # Things that won't work
    for bad_time in ["apple", "1.5h", "1s12h"]:
        with pytest.raises(ValueError):
            util.str2timedelta(bad_time)


def test_str2total_seconds():
    """Tests for str2total_seconds."""

    assert util.str2total_seconds("1234") == 1234
    assert util.str2total_seconds("567s") == 567
    assert util.str2total_seconds("9m") == 9 * 60
    assert util.str2total_seconds("1h30m") == 90 * 60
    assert util.str2total_seconds("1h12s") == 3612

    # Things that won't work
    for bad_time in ["apple", "1.5h", "1s12h"]:
        with pytest.raises(ValueError):
            util.str2total_seconds(bad_time)


def test_host_init():
    """Test creating Hosts."""

    assert util.Host("host:1234").url() == "http://host:1234/"
    assert util.Host("http://host:1234").url() == "http://host:1234/"
    assert util.Host("http://host:1234/").url() == "http://host:1234/"
    assert util.Host("http://host/").url() == "http://host/"

    assert str(util.Host("host:1234")) == "host:1234"
    assert str(util.Host("http://host:1234")) == "host:1234"
    assert str(util.Host("http://host:1234/")) == "host:1234"
    assert str(util.Host("http://host/")) == "host"

    # These don't work
    with pytest.raises(ValueError):
        util.Host(":1234")
    with pytest.raises(TypeError):
        util.Host(None)


def test_host_endpoint():
    """Test Host.join_endpoint."""

    assert util.Host("host:1234").join_endpoint("end/pt") == "http://host:1234/end/pt"
    assert (
        util.Host("http://host:1234").join_endpoint("end/pt")
        == "http://host:1234/end/pt"
    )
    assert (
        util.Host("http://host:1234/").join_endpoint("end/pt")
        == "http://host:1234/end/pt"
    )


def test_host_equality():
    """Test comparing Hosts."""

    assert util.Host("host:1234") == util.Host("host:1234")
    assert util.Host("http://host:1234") == util.Host("host:1234")
    assert util.Host("http://host:1234/") == util.Host("host:1234")


def test_host_hashing():
    """Test hashing Hosts."""

    # Hosts with the same hostname and port have the same hash
    assert {util.Host("host:1234"): "a"}.keys() == {util.Host("host:1234"): "b"}.keys()
    assert {util.Host("http://host:1234"): "a"}.keys() == {
        util.Host("host:1234"): "b"
    }.keys()
    assert {util.Host("http://host:1234/"): "a"}.keys() == {
        util.Host("host:1234"): "b"
    }.keys()


def test_ps_empty(fs):
    """Test empty Persistent State."""

    # By default, this doesn't work
    with pytest.raises(exceptions.InternalError):
        util.PersistentState(pathlib.Path("/missing/state"))

    # But this works
    ps = util.PersistentState(pathlib.Path("/missing/state"), missing_ok=True)
    assert ps.state == {}


def test_ps_set_to(fs):
    """Set setting PersistentState on init."""

    # Create existing file
    fs.create_file("/persistent/state.json", contents=json.dumps({"test": "value"}))

    ps = util.PersistentState(
        pathlib.Path("/persistent/state.json"), set_to={"new": "state"}
    )

    # State has been set
    assert ps.state == {"new": "state"}

    # Check the file on disk:
    with open("/persistent/state.json") as f:
        diskstate = json.load(f)
    assert diskstate == ps.state


def test_ps_read(fs):
    """Test trying to read persistent state from disk."""

    fs.create_file("/persistent/state.json", contents=json.dumps({"test": "value"}))

    ps = util.PersistentState(pathlib.Path("/persistent/state.json"))
    assert ps.state == {"test": "value"}


def test_ps_read_error(fs):
    """Test errors reading persistent state from disk."""

    # Invalid Json
    fs.create_file("/persistent/invalid.json", contents="{{{{{{")
    with pytest.raises(exceptions.InternalError):
        util.PersistentState(pathlib.Path("/persistent/invalid.json"))

    # I/O error
    fs.create_file("/persistent/permission.json", contents="{}")
    os.chmod("/persistent/permission.json", mode=0)
    with pytest.raises(exceptions.InternalError):
        util.PersistentState(pathlib.Path("/persistent/permission.json"))


def test_ps_noupdate(fs):
    """Test trying to set persistent state while not in update mode."""

    fs.create_file("/persistent/state.json", contents=json.dumps({"test": "value"}))

    ps = util.PersistentState(pathlib.Path("/persistent/state.json"))
    assert ps.state == {"test": "value"}

    with pytest.raises(RuntimeError):
        ps.state = {"new": "state"}

    assert ps.state == {"test": "value"}


def test_ps_update(fs):
    """Test trying to update a persistent state normally."""

    # Need a file to load the persistent state
    fs.create_file("/persistent/state.json", contents=json.dumps({"test": "value"}))

    ps = util.PersistentState(pathlib.Path("/persistent/state.json"))
    assert ps.state == {"test": "value"}

    with ps.update():
        ps.state = {"new": "state"}

    # Update worked.
    assert ps.state == {"new": "state"}

    # Check the file on disk:
    with open("/persistent/state.json") as f:
        diskstate = json.load(f)
    assert diskstate == ps.state


def test_ps_update_failed(fs):
    """Test rollback after a failed update."""

    fs.create_file("/persistent/state.json", contents=json.dumps({"test": "value"}))

    ps = util.PersistentState(pathlib.Path("/persistent/state.json"))
    assert ps.state == {"test": "value"}

    # Make the directory read-only
    os.chmod("/persistent", mode=0o0500)

    # Update fails
    with pytest.raises(exceptions.InternalError):
        with ps.update():
            ps.state = {"new": "state"}

    # State hasn't changed
    assert ps.state == {"test": "value"}

    # Check the file on disk
    with open("/persistent/state.json") as f:
        diskstate = json.load(f)
    assert diskstate == ps.state


def test_hash_dict():
    """Test hash_dict."""

    # These should have the same hash
    a = {"a": 1, "b": [{"c": 2, "d": 3}, {"e": 4, "f": 5}], "g": {"h": 6, "i": 7}}
    b = {"g": {"i": 7, "h": 6}, "b": [{"d": 3, "c": 2}, {"f": 5, "e": 4}], "a": 1}

    assert util.hash_dict(a) == util.hash_dict(b)

    # These are not
    a = {"a": 1, "b": [{"c": 2, "d": 3}, {"e": 4, "f": 5}], "g": {"h": 6, "i": 7}}
    b = {"a": 0, "b": [{"c": 2, "d": 3}, {"e": 4, "f": 5}], "g": {"h": 6, "i": 7}}

    assert util.hash_dict(a) != util.hash_dict(b)

    # Nore are these
    a = {"a": 1, "b": [{"c": 2, "d": 3}, {"e": 4, "f": 5}], "g": {"h": 6, "i": 7}}
    b = {"j": 1, "b": [{"c": 2, "d": 3}, {"e": 4, "f": 5}], "g": {"h": 6, "i": 7}}

    assert util.hash_dict(a) != util.hash_dict(b)


def test_hash_dict_value():
    """Check the values returned by hash_dict.

    The hash dict algorithm as three steps:
    * sort the keys of the input dict (see util.sort_dict)
    * serialize the data using MessagePack

        see https://github.com/msgpack/msgpack/blob/master/spec.md

    * Compute the MD5 hash of the serialized data.
    """

    # Here's our test dict
    a = {"g": {"i": 7, "h": 6}, "b": [{"d": 3, "c": 2}, {"f": 5, "e": 4}], "a": 1}
    # after running this through util.sort_dict and message packing, this becomes:
    #
    #    82 A1 61 01 A1 62 92 82 A1 63 02 A1 64 03 82
    #    A1 65 04 A1 66 05 A1 67 82 A1 68 06 A1 69 07
    #
    #  83           -- fixmap length 3
    #    A1 61      -- fixstr length 1 = "a"
    #    01         -- fixint = 1
    #    A1 62      -- fixstr length 1 = "b"
    #    92         -- fixarray length 2
    #      82       -- fixmap length 2
    #        A1 63  -- fixstr length 1 = "c"
    #        02     -- fixint = 2
    #        A1 64  -- fixstr length 1 = "d"
    #        03     -- fixint = 3
    #      82       -- fixmap length 2
    #        A1 65  -- fixstr length 1 = "e"
    #        04     -- fixint = 4
    #        A1 66  -- fixstr length 1 = "f"
    #        05     -- fixint = 5
    #    A1 67      -- fixstr length 1 = "g"
    #    82         -- fixmap length 2
    #      A1 68    -- fixstr length 1 = "h"
    #      06       -- fixint = 6
    #      A1 69    -- fixstr length 1 = "i"
    #      07       -- fixint = 7
    #
    # Given the above, it's easy to compute the MD5 hash of this packed data.  e.g.:
    #
    #   $ printf "%b%b" "\x83\xa1a\x01\xa1\x62\x92\x82\xa1\x63\x02\xa1\x64" \
    #   > "\x03\x82\xa1\x65\x04\xa1\x66\x05\xa1\x67\x82\xa1\x68\x06\xa1\x69\x07" \
    #   > | md5sum -
    #   dd18dea4349566ff0290e4d6aeb34035  -
    assert util.hash_dict(a) == "dd18dea4349566ff0290e4d6aeb34035"


def test_state(storage_path):
    """Test PersistentState.

    This is the original PersistentState test.  But now, some of
    the stuff tested here is also tested separately above.
    """

    # Create persistent state
    p = pathlib.Path(storage_path, "state.json")
    ps = util.PersistentState(p, missing_ok=True)

    # Test the default state
    assert ps.state == {}

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

    with pytest.raises(exceptions.InternalError) as excinfo:
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
