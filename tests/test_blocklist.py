"""Test coco.blocklist."""

import pathlib

import pytest

from coco.blocklist import Blocklist
from coco.exceptions import InvalidUsage
from coco.util import Host


@pytest.fixture
def blocklist(blocklist_path):
    """Create and return a Blocklist."""
    # Create the known hosts list
    hosts = ["testhost1:1234", "testhost1:2345", "testhost2:1234"]
    hosts = [Host(h) for h in hosts]

    # Create and return the blocklist
    return Blocklist(hosts, pathlib.Path(blocklist_path))


def test_add(blocklist):
    """Test adding things to the blocklist."""

    assert len(blocklist.hosts) == 0
    assert blocklist.add_hosts(["testhost1:1234"])

    assert len(blocklist.hosts) == 1
    assert Host("testhost1:1234") in blocklist.hosts

    assert blocklist.add_hosts(["testhost1:1234", "testhost2"])

    assert len(blocklist.hosts) == 2
    assert Host("testhost1:1234") in blocklist.hosts
    assert Host("testhost2:1234") in blocklist.hosts

    current_hosts = blocklist.hosts

    # Try and add an unknown host
    with pytest.raises(InvalidUsage):
        blocklist.add_hosts(["fakehost:1234"])
    assert blocklist.hosts == current_hosts

    # Try and add a non-unique hosts
    with pytest.raises(InvalidUsage):
        blocklist.add_hosts(["testhost1"])
    assert blocklist.hosts == current_hosts


def test_remove(blocklist):
    """Guess what this does."""

    assert blocklist.add_hosts(["testhost1:1234", "testhost2"])
    assert len(blocklist.hosts) == 2

    assert blocklist.remove_hosts(["testhost2"])
    assert len(blocklist.hosts) == 1
    assert Host("testhost1:1234") in blocklist.hosts
    assert Host("testhost2:1234") not in blocklist.hosts

    assert blocklist.remove_hosts(["testhost1:2345"])
    assert len(blocklist.hosts) == 1
    assert Host("testhost1:1234") in blocklist.hosts
    assert Host("testhost1:2345") not in blocklist.hosts

    current_hosts = blocklist.hosts

    # Try and add an unknown host
    with pytest.raises(InvalidUsage):
        blocklist.remove_hosts(["fakehost:1234"])
    assert blocklist.hosts == current_hosts


def test_clear(blocklist):
    """Test clearing the blocklist."""

    assert blocklist.add_hosts(["testhost1:1234", "testhost2"])
    assert len(blocklist.hosts) == 2

    assert blocklist.clear_hosts()
    assert len(blocklist.hosts) == 0
