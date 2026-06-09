"""Common test fixtures"""

import json
import traceback

import pytest
import yaml

from coco import config, core

pytest_plugins = ["coco_runner", "rest_server"]

# Default test config used in the coco_config fixture
DEFAULT_TEST_CONFIG = {
    "host": "cocohost",
    "endpoint_dir": "/etc/coco/endpoints",
    "groups": {"defgroup": ["host:1234"]},
    "comet_broker": {"enabled": False},
}


def pytest_configure(config):
    """This function extends the pytest config file."""

    config.addinivalue_line(
        "markers",
        "no_default_config(flag): "
        "If flag is True, the default test config is not used.",
    )


@pytest.fixture
def coco_config(request, fs):
    """Fixture creating the config file for CLI tests.

    Yields a function which can be called to add more config to the
    coco config file at runtime:

    def test_something(coco_config):
        coco_config({"more": "config"})
    """

    # Check whether to skip the default config
    marker = request.node.get_closest_marker("no_default_config")
    if marker is not None:
        no_default_config = bool(marker.args[0])
    else:
        no_default_config = False

    if no_default_config:
        _config = {}
    else:
        _config = DEFAULT_TEST_CONFIG

    # Create the directory for the coco config file.
    fs.create_dir("/etc/coco")

    def _write_config(extra_config={}):
        """Helper function to add extra config to the coco config file."""
        nonlocal _config

        # Append to existing config
        if extra_config:
            if not isinstance(extra_config, dict):
                raise RuntimeError("non-dict passed to coco_config().")
            _config = config.merge_dict_tree(_config, extra_config)

        # If there's no config, create nothing.
        if _config:
            # Dump it to a file
            with open("/etc/coco/coco.conf", "w") as f:
                yaml.dump(_config, f)

    # Write the config, if any
    _write_config()

    # Create a default endpoint, so something's there.
    fs.create_file(
        "/etc/coco/endpoints/endpoint.conf", contents=yaml.dump({"group": "defgroup"})
    )

    # Yield the function so test can update the config
    return _write_config


@pytest.fixture
def mock_comet(rest_server):
    """Yields a mocked comet broker."""

    def _register_state(route, body):
        """Pretend to be comet's /register-state endpoint."""

        # Decode body
        body = json.loads(body)

        return {"result": "success", "request": "get_state", "hash": body["hash"]}

    # Create a mock broker
    comet_broker = rest_server()

    # Add comet endpoints
    comet_broker.add_route("/register-state", method="POST", callback=_register_state)
    comet_broker.add_route("/send-state", method="POST", response={"result": "success"})

    # Start the mock
    comet_broker.start()

    # Yield the comet broker mock.
    yield comet_broker

    # Ensure server is shut down
    comet_broker.shutdown()


@pytest.fixture
def blocklist_path(fs):
    """Ensure the blocklist file exists.

    Yields the path to the file.
    """
    blocklist = "/var/lib/coco/blocklist.json"
    fs.create_file(blocklist, contents="{}")

    return blocklist


@pytest.fixture
def storage_path(fs):
    """Ensure the storage path exist.

    Yields the path.
    """
    # storage_path
    storage_path = "/var/lib/coco/state/"
    fs.create_dir(storage_path)

    return storage_path


@pytest.fixture
def cocod(coco_config, blocklist_path, storage_path):
    """Set up coco daemon tests using click

    Yields a wrapper around click.testing.CliRunner().invoke.
    The first parameter passed to the wrapper should be
    the expected exit code.  Other parameters are passed
    to CliRunner.invoke (including the list of command
    line parameters).

    The wrapper performs rudimentary checks on the result,
    then returns the click.result so the caller can inspect
    the result further, if desired.

    For running cocod in general, use the coco_runner fixture.
    This fixture should only be used for cocod runs which
    are guaranteed to exit before trying to start Sanic (which
    will fail, if attempted).  In such cases, this fixture will
    run significantly faster than the same test performed using
    the coco_runner.
    """

    from click.testing import CliRunner

    # Create the runner before the test starts
    runner = CliRunner()

    def _cli_wrapper(expected_result, *args, **kwargs):
        nonlocal runner

        result = runner.invoke(core.cocod, *args, **kwargs)

        # Show traceback if one was created
        if (
            result.exit_code
            and result.exc_info
            and type(result.exception) is not SystemExit
        ):
            traceback.print_exception(*result.exc_info)

        # Print output so it appears in the test log on failure
        print(result.output)

        assert result.exit_code == expected_result
        if expected_result:
            assert type(result.exception) is SystemExit
        else:
            assert result.exception is None

        return result

    yield _cli_wrapper
