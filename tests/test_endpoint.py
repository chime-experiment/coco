"""Endpoint config tests."""

import json

import pytest
import yaml

from coco.state import ACTIVE


@pytest.fixture
def set_state(fs, storage_path):
    """Yields a function to set the active state."""

    def _set_state(state):
        fs.create_file(f"{storage_path}/{ACTIVE}", contents=json.dumps(state))

    return _set_state


@pytest.fixture
def set_endpoint(fs, coco_config):
    """Yields a endpoint-creating function.

    Use it like this:

    def test_something(set_endpoint):
        set_endpoint("group": "something"})
    """

    def _set_endpoint(config, skeleton=True):
        if skeleton:
            endpoint = {"group": "defgroup"}
        else:
            endpoint = {}

        with open("/etc/coco/endpoints/endpoint.conf", "w") as f:
            f.write(yaml.dump(endpoint | config))

    return _set_endpoint


def test_spurious_name(set_endpoint, cocod):
    """An endpoint file can't define a "name"."""
    set_endpoint({"name": "name"})
    result = cocod(1, ["--check-config"])
    assert "name" in result.output


def test_invalid_parameter(set_endpoint, cocod):
    """Invalid endpoint parameters aren't allowed."""
    set_endpoint({"calable": True})
    result = cocod(1, ["--check-config"])
    assert "calable" in result.output


def test_boolean(set_endpoint, cocod):
    """Test boolean parameters in endpoint."""

    for param in ("callable", "call_on_start", "enforce_group", "report_latency"):
        print(param)
        set_endpoint({param: "maybe"})
        result = cocod(1, ["--check-config"])
        assert param in result.output
        assert "boolean" in result.output
        set_endpoint({param: True})
        result = cocod(0, ["--check-config"])


def test_report_type(set_endpoint, cocod):
    """Check for invalid report_type."""
    set_endpoint({"report_type": "INVALID_TYPE"})
    result = cocod(1, ["--check-config"])
    assert "unknown report_type" in result.output


def test_missing_group(set_endpoint, cocod):
    """Endpoint group must be defined."""

    set_endpoint({"group": "MISSING_GROUP"}, skeleton=False)
    result = cocod(1, ["--check-config"])
    assert "MISSING_GROUP" in result.output


def test_implicit_forward_no_group(set_endpoint, cocod):
    """Check missing group with implicit forward.

    The implicit forward happens when ther is
    no `all.forwards` defined in the file
    """

    set_endpoint({}, skeleton=False)
    result = cocod(1, ["--check-config"])
    assert "call: forward: null" in result.output

    # But this is okay
    set_endpoint({"group": "defgroup"}, skeleton=False)
    result = cocod(0, ["--check-config"])

    # And this, too
    set_endpoint({"call": {"forward": None}}, skeleton=False)
    result = cocod(0, ["--check-config"])


def test_ext_forward_no_group(set_endpoint, cocod):
    """Check missing group with external forward."""

    set_endpoint({"call": {"forward": "somewhere"}}, skeleton=False)
    result = cocod(1, ["--check-config"])
    assert "group" in result.output


def test_call_dict(set_endpoint, cocod):
    """Call must be a dict"""
    set_endpoint(
        {
            "call": True,
        }
    )
    result = cocod(1, ["--check-config"])
    assert "call" in result.output


def test_call_keys(set_endpoint, cocod):
    """Check allowed keys in "call."""
    set_endpoint({"call": {"something": "bad"}})
    result = cocod(1, ["--check-config"])
    assert "call" in result.output


def test_call_types(set_endpoint, cocod):
    """Check typing for calls.

    Only string and mapping are allowed"""

    set_endpoint({"call": {"forward": [["list1", "list2"]]}})
    result = cocod(1, ["--check-config"])
    assert "external forward" in result.output

    set_endpoint({"call": {"coco": [["list1", "list2"]]}})
    result = cocod(1, ["--check-config"])
    assert "internal forward" in result.output

    set_endpoint({"before": [["list1", "list2"]]})
    result = cocod(1, ["--check-config"])
    assert "before action" in result.output

    set_endpoint({"after": [["list1", "list2"]]})
    result = cocod(1, ["--check-config"])
    assert "after action" in result.output


def test_forward_no_name(set_endpoint, cocod):
    """Mapping forwards must have a name."""

    set_endpoint({"call": {"forward": {"no_name": "nothing"}}})
    result = cocod(1, ["--check-config"])
    assert "external forward" in result.output

    set_endpoint({"call": {"coco": {"no_name": "nothing"}}})
    result = cocod(1, ["--check-config"])
    assert "internal forward" in result.output

    set_endpoint({"before": {"no_name": "nothing"}})
    result = cocod(1, ["--check-config"])
    assert "before action" in result.output

    set_endpoint({"after": {"no_name": "nothing"}})
    result = cocod(1, ["--check-config"])
    assert "after action" in result.output


def test_internal_forward_missing(set_endpoint, cocod):
    """Internal forwards must exist."""

    set_endpoint({"call": {"coco": "BAD_ENDPOINT"}})
    result = cocod(1, ["--check-config"])
    assert "BAD_ENDPOINT" in result.output

    set_endpoint({"call": {"coco": {"name": "BAD_ENDPOINT"}}})
    result = cocod(1, ["--check-config"])
    assert "BAD_ENDPOINT" in result.output

    set_endpoint({"before": "BAD_ENDPOINT"})
    result = cocod(1, ["--check-config"])
    assert "BAD_ENDPOINT" in result.output

    set_endpoint({"after": {"name": "BAD_ENDPOINT"}})
    result = cocod(1, ["--check-config"])
    assert "BAD_ENDPOINT" in result.output


def test_save_reply_to_state_type(set_endpoint, cocod):
    """save_reply_to_state must be a string or dict."""

    set_endpoint({"call": {"forward": {"name": "name", "save_reply_to_state": []}}})
    result = cocod(1, ["--check-config"])
    assert "save_reply_to_state" in result.output

    # but this is fine.
    set_endpoint(
        {
            "call": {
                "forward": {"name": "name", "save_reply_to_state": {"path": "value"}}
            }
        }
    )
    result = cocod(0, ["--check-config"])

    # also this
    set_endpoint({"call": {"forward": {"name": "name", "save_reply_to_state": "path"}}})
    result = cocod(0, ["--check-config"])


def test_on_failrue(set_endpoint, cocod):
    """Test on_failure config checks."""

    # Must be a dict
    set_endpoint({"call": {"forward": {"name": "name", "on_failure": True}}})
    result = cocod(1, ["--check-config"])
    assert "on_failure" in result.output

    # Only allowed keys are "call" and "call_single_host"
    set_endpoint(
        {"call": {"forward": {"name": "name", "on_failure": {"something": "else"}}}}
    )
    result = cocod(1, ["--check-config"])
    assert "on_failure" in result.output

    # Values must be strings
    set_endpoint(
        {
            "call": {
                "forward": {
                    "name": "name",
                    "on_failure": {"call_single_host": ["list"]},
                }
            }
        }
    )
    result = cocod(1, ["--check-config"])
    assert "call_single_host" in result.output


def test_on_failure_missing_endpoint(set_endpoint, cocod):
    """On-failure endpoints must exist."""

    set_endpoint(
        {
            "call": {
                "forward": {
                    "name": "name",
                    "on_failure": {
                        "call": "BAD_ENDPOINT",
                        "call_single_host": "endpoint",
                    },
                }
            }
        }
    )
    result = cocod(1, ["--check-config"])
    assert "BAD_ENDPOINT" in result.output

    set_endpoint(
        {
            "call": {
                "forward": {
                    "name": "name",
                    "on_failure": {
                        "call_single_host": "BAD_ENDPOINT",
                        "call": "endpoint",
                    },
                }
            }
        }
    )
    result = cocod(1, ["--check-config"])
    assert "BAD_ENDPOINT" in result.output


def test_forward_reply(set_endpoint, cocod):
    """Test reply check config checks."""

    # Must be a dict
    set_endpoint({"call": {"forward": {"name": "name", "reply": True}}})
    result = cocod(1, ["--check-config"])
    assert "reply" in result.output

    # Invalid checks are not allowed
    set_endpoint(
        {"call": {"forward": {"name": "name", "reply": {"something": "else"}}}}
    )
    result = cocod(1, ["--check-config"])
    assert "reply" in result.output


def test_values_type(set_endpoint, cocod):
    """Check Endpoint "values" type checking.

    It's either a dict-of-types or a list-of-dicts
    """

    # List of strings is not allowed
    set_endpoint({"values": ["value1", "value2"]})
    result = cocod(1, ["--check-config"])
    assert "values" in result.output

    # dict of lists is not allowed
    set_endpoint({"values": {"value1": {"type": "int"}}})
    result = cocod(1, ["--check-config"])
    assert "value1" in result.output


def test_values_types(set_endpoint, cocod):
    """Test endpoint value types."""

    # These are the only allowed types
    for type_ in ("str", "dict", "int", "float", "bool", "list"):
        set_endpoint({"values": {"good_value": type_}})
        cocod(0, ["--check-config"])

    # Other types are not allowed
    for type_ in ("set", "tuple", "coco", "something_weird"):
        set_endpoint({"values": {"bad_value": type_}})
        result = cocod(1, ["--check-config"])
        assert "bad_value" in result.output


def test_timestamp(set_endpoint, cocod):
    """Timestamp must be a string."""

    set_endpoint({"timestamp": {"key": "value"}})
    result = cocod(1, ["--check-config"])
    assert "timestamp" in result.output


def test_save_state_no_values(set_endpoint, cocod):
    """save_state must be used with values."""

    set_endpoint({"save_state": "path"})
    result = cocod(1, ["--check-config"])
    assert "'save_state' with no 'values'" in result.output


def test_save_state_wrong_type(set_endpoint, set_state, cocod):
    """Check save_state with wrong value type."""

    set_endpoint({"save_state": "path/subpath", "values": {"item": "int"}})
    set_state({"path": {"subpath": {"item": "string"}}})

    result = cocod(1, ["--check-config"])
    assert "state at '/path/subpath'" in result.output
    assert "has type" in result.output


def test_send_state_wrong_type(set_endpoint, set_state, cocod):
    """Check send_state with wrong value type."""

    set_endpoint({"send_state": "path/subpath", "values": {"item": "int"}})
    set_state({"path": {"subpath": {"item": "string"}}})

    result = cocod(1, ["--check-config"])
    assert "state at '/path/subpath'" in result.output
    assert "has type" in result.output


def test_schedule_values(set_endpoint, cocod):
    """Can't set both schedule and values."""

    set_endpoint({"schedule": {"period": "1h"}, "values": {"item": "int"}})
    result = cocod(1, ["--check-config"])
    assert "both 'schedule' and 'values'" in result.output


def test_schedule_nodict(set_endpoint, cocod):
    """Schedule must be a dict."""

    set_endpoint({"schedule": ["1h"]})
    result = cocod(1, ["--check-config"])
    assert "expected mapping" in result.output


def test_schedule_params(set_endpoint, cocod):
    """Reject extra schedule parameters."""

    set_endpoint({"schedule": {"poriod": "1h"}})
    result = cocod(1, ["--check-config"])
    assert "poriod" in result.output


def test_bad_schedule_period(set_endpoint, cocod):
    """Reject bad schedule periods."""

    set_endpoint({"schedule": {"period": "weekly"}})
    result = cocod(1, ["--check-config"])
    assert "period" in result.output

    set_endpoint({"schedule": {"period": [1, 2, 3]}})
    result = cocod(1, ["--check-config"])
    assert "period" in result.output

    set_endpoint({"schedule": {"period": -5}})
    result = cocod(1, ["--check-config"])
    assert "period" in result.output

    set_endpoint({"schedule": {"period": 0}})
    result = cocod(1, ["--check-config"])
    assert "period" in result.output


def test_schedule_condition_nodict(set_endpoint, cocod):
    """Check bad require_state type."""

    set_endpoint({"schedule": {"period": "1h", "require_state": [1, 2, 3]}})
    result = cocod(1, ["--check-config"])
    assert "require_state" in result.output


def test_schedule_condition_extra_param(set_endpoint, cocod):
    """Check bad keys in require_state."""

    set_endpoint(
        {
            "schedule": {
                "period": "1h",
                "require_state": {"tpye": "int", "path": "somewhere"},
            }
        }
    )
    result = cocod(1, ["--check-config"])
    assert "tpye" in result.output


def test_schedule_condition_missing_param(set_endpoint, cocod):
    """require_state entries must have both type and path"""

    set_endpoint({"schedule": {"period": "1h", "require_state": {"path": "somewhere"}}})
    result = cocod(1, ["--check-config"])
    assert "'type' missing" in result.output

    set_endpoint({"schedule": {"period": "1h", "require_state": [{"type": "int"}]}})
    result = cocod(1, ["--check-config"])
    assert "'path' missing" in result.output


def test_schedule_condition_bad_type(set_endpoint, cocod):
    """check require_state type checking"""

    set_endpoint(
        {
            "schedule": {
                "period": "1h",
                "require_state": {"type": "tuple", "path": "somewhere"},
            }
        }
    )
    result = cocod(1, ["--check-config"])
    assert "unknown 'require_state' type" in result.output


def test_endpoint_rewrite(coco_runner):
    """Test the rewriting of endpoint config.

    We do this by checking what was given to the client.
    """

    # Create a target group
    coco_runner.add_targets("test-group", 1)

    # Set the state so the endpoints have something to point to.
    coco_runner.set_state(
        {"base": {"send": {}, "save": {}, "get": {}, "set": {}, "false": False}}
    )

    # Some endpoints to check.  This is a dict of 2-tuples.  The first element
    # of the tuple is the dict as written to the JSON config file.  The second
    # is what should be in the config when the client retrieves it.  Dict keys
    # are endpoint names

    endpoints = {
        # Minimal endpoint
        "min": (
            {"call": {"forward": None}},
            {
                "call": {"forward": None},
                "call_on_start": False,
                "callable": True,
                "description": "NO DESCRIPTION",
                "enforce_group": False,
                "report_latency": True,
                "report_type": "CODES_OVERVIEW",
                "type": "GET",
            },
        ),
        # Maximal endpoint
        "all": (
            {
                "description": "Maximal endpoint",
                "enforce_group": True,
                "group": "test-group",
                "type": "POST",
                "report_type": "FULL",
                "call": {
                    "forward": ["endp1", "endp2"],
                    "coco": "min",
                },
                "before": "min",
                "after": "min",
                "callable": False,
                "call_on_start": False,
                "values": {
                    "param1": "int",
                    "param2": "dict",
                    "param3": "str",
                },
                "send_state": "base/send",
                "save_state": "base/save",
                "get_state": "base/get",
                "set_state": {
                    "base/set": True,
                },
                "report_latency": False,
                "timestamp": "base/time",
            },
            {
                "after": ["min"],
                "before": ["min"],
                "call": {
                    "forward": ["endp1", "endp2"],
                    "coco": ["min"],
                },
                "call_on_start": False,
                "callable": False,
                "description": "Maximal endpoint",
                "enforce_group": True,
                "get_state": "base/get",
                "group": "test-group",
                "report_latency": False,
                "report_type": "FULL",
                "save_state": ["base/save"],
                "send_state": "base/send",
                "set_state": {"base/set": True},
                "type": "POST",
                "values": {
                    "param1": "int",
                    "param2": "dict",
                    "param3": "str",
                },
                "timestamp": "base/time",
            },
        ),
        "scheduled": (
            {
                "group": "test-group",
                "description": "schedule config test",
                "schedule": {
                    "period": "1h",
                    "require_state": [
                        {
                            "path": "base/false",
                            "type": "bool",
                            "value": True,
                        },
                    ],
                },
            },
            {
                "call_on_start": False,
                "callable": True,
                "description": "schedule config test",
                "enforce_group": False,
                "group": "test-group",
                "report_latency": True,
                "report_type": "CODES_OVERVIEW",
                "schedule": {
                    "period": 3600.0,
                    "require_state": [
                        {
                            "path": "base/false",
                            "type": "bool",
                            "value": True,
                        },
                    ],
                },
                "type": "GET",
            },
        ),
    }

    # Add endpoints
    for name, endpoint in endpoints.items():
        coco_runner.add_endpoint(name, endpoint[0])

    result = coco_runner.client("--json", "config", "get")

    # De-JSONify
    config = json.loads(result.stdout)
    assert "endpoints" in config

    for endpoint in config["endpoints"]:
        # Pop endpoint name out of the config
        name = endpoint["name"]
        del endpoint["name"]

        # Should be one of the endpoints we expected
        assert name in endpoints

        original = endpoints[name][1]

        # Update the "values" dict, in the origina endpoint, if present
        if "values" in original:
            if isinstance(original["values"], dict):
                values = {
                    name: {"type": type_, "option": True}
                    for name, type_ in original["values"].items()
                }
            else:
                values = {}
                for item in original["values"]:
                    name = item["name"]
                    del item["name"]
                    if "option" not in item:
                        item["option"] = True

                    values[name] = item
            original["values"] = values

        # Check the config
        assert endpoint == original, f"Mismatch for endpoint {name!r}"
