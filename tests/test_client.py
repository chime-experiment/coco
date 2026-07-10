"Test the coco client"

import json


def test_help_no_endpoints(coco_runner):
    """Check --help with no endpoints.

    In this case, the --help-config hint
    should be shown.
    """
    # These should both show the hint becasue
    # there are no endpoints defined.
    result = coco_runner.client("--help", no_daemon=True)
    assert "--help-config" in result.stdout
    result = coco_runner.client("--help", no_daemon=True, no_backend=True)
    assert "--help-config" in result.stdout


def test_help(coco_runner):
    coco_runner.add_targets("cluster", 1)
    coco_runner.add_endpoint(
        "nop",
        endpoint_def={
            "description": "Do nothing.",
            "call": {"forward": None},
        },
    )

    # These should all complete successfully
    coco_runner.client("--help")
    coco_runner.client("blocklist", "--help")
    coco_runner.client("blocklist", "add", "--help")
    coco_runner.client("nop", "--help")


def test_style(coco_runner):
    """Test the --json and "--yaml flags.

    And also the deprecated --style option.
    """
    from coco.util import yaml_load

    coco_runner.add_targets("cluster", 1)
    coco_runner.add_endpoint("nop", {"call": {"forward": None}})

    # Explicitly start the daemon early so we can properly generate
    # expected_result
    coco_runner.start_daemon()

    expected_result = {
        "endpoint": f"http://127.0.0.1:{coco_runner.port}/nop",
        "method": "GET",
        "data": {"coco_report_type": "CODES_OVERVIEW"},
    }

    # Default is yaml
    result = yaml_load(coco_runner.client("--show-call-only", "nop").output)
    assert result == expected_result

    result = json.loads(coco_runner.client("--show-call-only", "--json", "nop").output)
    assert result == expected_result

    result = yaml_load(coco_runner.client("--show-call-only", "--yaml", "nop").output)
    assert result == expected_result

    result = json.loads(
        coco_runner.client("--show-call-only", "--style", "json", "nop").output
    )
    assert result == expected_result

    result = yaml_load(
        coco_runner.client("--show-call-only", "--style", "yaml", "nop").output
    )
    assert result == expected_result

    # Invalid --style values are silently ignored
    result = yaml_load(
        coco_runner.client("--show-call-only", "--style", "jason", "nop").output
    )
    assert result == expected_result


def test_show_call(coco_runner):
    """Test the --show-call-only flag."""

    coco_runner.add_targets("cluster", 1)
    coco_runner.add_endpoint("nop", {"call": {"forward": None}})

    # A normal endpoint
    result = json.loads(coco_runner.client("--show-call-only", "--json", "nop").output)
    assert result == {
        "endpoint": f"http://127.0.0.1:{coco_runner.port}/nop",
        "method": "GET",
        "data": {"coco_report_type": "CODES_OVERVIEW"},
    }

    # A local endpoint
    result = json.loads(
        coco_runner.client(
            "--show-call-only", "--json", "blocklist", "add", "HOST"
        ).output
    )
    assert result == {
        "endpoint": f"http://127.0.0.1:{coco_runner.port}/update-blocklist",
        "method": "GET",
        "data": {
            "command": "add",
            "hosts": ["HOST"],
            "coco_report_type": "CODES_OVERVIEW",
        },
    }

    # coco config -- the endpoint here is not called, but --show-call-only
    # should still show it
    result = json.loads(
        coco_runner.client("--show-call-only", "--json", "config", "get").output
    )
    assert result == {
        "endpoint": f"http://127.0.0.1:{coco_runner.port}/config",
        "method": "GET",
    }


def test_endpoint_command(coco_runner):
    """Test the rudiments of the EndpointCommand.

    Specificaly:
    * --help output
    * argument ingestion
    * missing argument handling
    """

    coco_runner.add_targets("cluster", 1)
    coco_runner.add_endpoint(
        "endpoint",
        {
            "group": "cluster",
            "type": "POST",
            "values": [
                {"name": "bool", "type": "bool"},
                {"name": "str", "type": "str"},
                {"name": "int", "type": "int"},
                {"name": "float", "type": "float"},
                {"name": "list", "type": "list[int]", "option": False},
                {"name": "dict", "type": "dict"},
            ],
        },
    )

    # Check the help output.  It's not terribly informative, but it should all be there.
    result = coco_runner.client("endpoint", "--help").output
    # click help text uppercases all arguments
    assert "--str" in result
    assert "--int" in result
    assert "--float" in result
    assert "LIST" in result
    assert "--dict" in result
    assert "--bool" in result

    # Not providing parameters results in a usage error (=2)
    coco_runner.client("endpoint", expect_failure=True)

    # Partial parameters is still an error
    result = coco_runner.client(
        "endpoint",
        '--dict={"object": "value"}',
        "--float=1.1",
        "--int=1",
        "--str=str",
        "1",
        "2",
        "3",
        expect_failure=True,
    )
    assert "parameter '--bool'" in result.output

    result = coco_runner.client(
        "endpoint",
        "--bool",
        "--float=1.1",
        "--int=1",
        "--str=str",
        "1",
        "2",
        "3",
        expect_failure=True,
    )
    assert "parameter '--dict'" in result.output

    # Bad dict -- syntax error
    result = coco_runner.client(
        "endpoint",
        "--dict={1: 2: 3}",
        "--float=1.1",
        "--int=4",
        "1",
        "2",
        "3",
        "--str=abc",
        "--bool",
        expect_failure=True,
    )
    assert "Failure parsing '--dict'" in result.output

    # Also a parsing error because bareword "scalar" without quotation marks is
    # not a string in JSON
    result = coco_runner.client(
        "endpoint",
        "--dict=scalar",
        "--float=1.1",
        "--int=4",
        "1",
        "--str=abc",
        "--bool",
        expect_failure=True,
    )
    assert "Failure parsing '--dict'" in result.output

    result = coco_runner.client(
        "endpoint",
        "--dict=3",
        "--float=1.1",
        "--int=4",
        "1",
        "--str=abc",
        "--bool",
        expect_failure=True,
    )
    assert "Invalid value for '--dict'" in result.output

    result = coco_runner.client(
        "endpoint",
        '--dict={"object": "value"}',
        "--float=pi",
        "--int=4",
        "1",
        "--str=abc",
        "--bool",
        expect_failure=True,
    )
    assert "Invalid value for '--float'" in result.output

    # Notably here an integer float works
    result = coco_runner.client(
        "endpoint",
        '--dict={"object": "value"}',
        "--float=1",
        "--int=4.4",
        "1",
        "--str=abc",
        "--bool",
        expect_failure=True,
    )
    assert "Invalid value for '--int'" in result.output

    result = coco_runner.client(
        "endpoint",
        '--dict={"object": "value"}',
        "--float=1.1",
        "--int=4",
        "[1,2,3]",
        "--str=abc",
        "--bool",
        expect_failure=True,
    )
    assert "Invalid value for 'LIST...'" in result.output


def test_value_handling(coco_runner):
    """End-to-end test of endpoint value handling."""

    coco_runner.add_targets("cluster", 1)
    coco_runner.add_endpoint(
        "endpoint",
        {
            "group": "cluster",
            "type": "POST",
            "values": {
                "bool": "bool",
                "str": "str",
                "int": "int",
                "float": "float",
                "list": "list[int]",
                "dict": "dict",
            },
        },
    )

    # Send data to the endpoint
    result = coco_runner.client(
        "--quiet",
        "--json",
        "endpoint",
        '--dict={"object": "value"}',
        "--float=1.1",
        "--int=4",
        "--list=1",
        "--list=2",
        "--list=3",
        "--str=abc",
        "--bool",
    )
    result = json.loads(result.stdout)
    assert result["success"]
    assert result["endpoint"]["200"] == 1

    # JSON-decoded version of the input data for testing against
    data = {
        "bool": True,
        "dict": {"object": "value"},
        "float": 1.1,
        "int": 4,
        "list": [1, 2, 3],
        "str": "abc",
    }

    # Data should have made it to the rest_server kotekan target stand-in
    target = coco_runner.targets[0]
    assert target.hit_count("/endpoint") == 1
    hit = target.hits("/endpoint")[0]
    assert hit.method == "POST"
    assert hit.request == data
    assert hit.response == {"path": "/endpoint", "result": "success", "body": data}
