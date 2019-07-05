"""Test the blacklist, in case you didn't get that from the filename."""
import logging

import pytest

from coco.blacklist import Blacklist
from coco.util import Host
from coco.exceptions import InvalidUsage

logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def blacklist(tmp_path):
    """Okay pydocstyle, you're killing me. Let me think what this does.

    Could it be a fixture that creates a blacklist for testing?
    """
    # Create the known hosts list
    hosts = ["testhost1:1234", "testhost1:2345", "testhost2:1234"]
    hosts = [Host(h) for h in hosts]

    # Create and return the blacklist
    return Blacklist(hosts, tmp_path / "blacklist.json")


def test_add(blacklist):
    """These lines of code test removing from the blacklist. No... wait... *adding* things."""

    assert len(blacklist.hosts) == 0
    assert blacklist.add_hosts(["testhost1:1234"])

    assert len(blacklist.hosts) == 1
    assert Host("testhost1:1234") in blacklist.hosts

    assert blacklist.add_hosts(["testhost1:1234", "testhost2"])

    assert len(blacklist.hosts) == 2
    assert Host("testhost1:1234") in blacklist.hosts
    assert Host("testhost2:1234") in blacklist.hosts

    current_hosts = blacklist.hosts

    # Try and add an unknown host
    with pytest.raises(InvalidUsage):
        blacklist.add_hosts(["fakehost:1234"])
    assert blacklist.hosts == current_hosts

    # Try and add a non-unique hosts
    with pytest.raises(InvalidUsage):
        blacklist.add_hosts(["testhost1"])
    assert blacklist.hosts == current_hosts


def test_remove(blacklist):
    """Guess what this does."""

    assert blacklist.add_hosts(["testhost1:1234", "testhost2"])
    assert len(blacklist.hosts) == 2

    assert blacklist.remove_hosts(["testhost2"])
    assert len(blacklist.hosts) == 1
    assert Host("testhost1:1234") in blacklist.hosts
    assert Host("testhost2:1234") not in blacklist.hosts

    assert blacklist.remove_hosts(["testhost1:2345"])
    assert len(blacklist.hosts) == 1
    assert Host("testhost1:1234") in blacklist.hosts
    assert Host("testhost1:2345") not in blacklist.hosts

    current_hosts = blacklist.hosts

    # Try and add an unknown host
    with pytest.raises(InvalidUsage):
        blacklist.remove_hosts(["fakehost:1234"])
    assert blacklist.hosts == current_hosts


def test_clear(blacklist):
    """."""

    assert blacklist.add_hosts(["testhost1:1234", "testhost2"])
    assert len(blacklist.hosts) == 2

    assert blacklist.clear_hosts()
    assert len(blacklist.hosts) == 0
