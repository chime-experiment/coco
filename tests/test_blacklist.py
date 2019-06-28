import logging

import pytest

from coco.blacklist import Blacklist
from coco.util import Host
from coco.exceptions import InvalidUsage

logging.basicConfig(level=logging.DEBUG)

@pytest.fixture
def blacklist(tmp_path):
    # Create the known hosts list
    hosts = ["testhost1:1234", "testhost1:2345", "testhost2:1234"]
    hosts = [Host(h) for h in hosts]

    # Create and return the blacklist
    return Blacklist(hosts, tmp_path / "blacklist.json")


def test_add(blacklist):

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

    assert blacklist.add_hosts(["testhost1:1234", "testhost2"])
    assert len(blacklist.hosts) == 2

    assert blacklist.clear_hosts()
    assert len(blacklist.hosts) == 0
