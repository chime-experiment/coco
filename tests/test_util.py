"""Unit tests for coco.util."""

import json
import os
import pathlib
from datetime import timedelta

import pytest

from coco import util


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

    ps = util.PersistentState(pathlib.Path("/missing/state"))
    assert ps.state == {}


def test_ps_read(fs):
    """Test trying to read persistent state from disk."""

    fs.create_file("/persistent/state.json", contents=json.dumps({"test": "value"}))

    ps = util.PersistentState(pathlib.Path("/persistent/state.json"))
    assert ps.state == {"test": "value"}


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
    with pytest.raises(RuntimeError):
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
