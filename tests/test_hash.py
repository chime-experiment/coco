"""Test the state hashing."""

import json
import os
from subprocess import Popen, PIPE
import yaml

from coco.util import hash_dict

path = os.path.dirname(os.path.abspath(__file__))
cmd = "{}/hash".format(path)


def test_simple_hash():
    """Test if hashed state is the same as in the C++ implementation."""

    config = dict(a=1, b="foo")
    cpphasher = Popen([cmd, json.dumps(config)], stdout=PIPE)
    cpphasher.wait()
    cpphash = cpphasher.stdout.readline().decode()

    # remove the \n at the end of the line
    cpphash = cpphash[:-1]

    assert cpphash == hash_dict(config)


def test_big_config_hash():
    """Test if hashed kotekan config is the same as in the C++ implementation."""

    config = yaml.safe_load(open("{}/config.yaml".format(path)))
    cpphasher = Popen([cmd, json.dumps(config)], stdout=PIPE, stderr=PIPE)
    cpphasher.wait()
    (cpphash, error) = cpphasher.communicate()
    cpphash = cpphash.decode()
    if error:
        print(error)

    # remove the \n at the end of the line
    cpphash = cpphash[:-1]

    assert cpphash == hash_dict(config)
