"""Common test fixtures"""

import traceback

import pytest
import yaml

from coco import config


def pytest_configure(config):
    """This function extends the pytest config file."""

    config.addinivalue_line(
        "markers",
        "no_default_config(*flag): "
        "If flag is True, the default test config is not used.",
    )
    config.addinivalue_line(
        "markers",
        "coco_config(*config_dict): "
        "used to set the coco.config for testing.  config_dict"
        "is merged with the default config.",
    )


@pytest.fixture
def coco_config(request, fs):
    """Fixture creating the config file for CLI tests."""

    # Check whether to skip the default config
    marker = request.node.get_closest_marker("no_default_config")
    if marker is not None:
        no_default_config = bool(marker.args[0])
    else:
        no_default_config = False

    if no_default_config:
        _config = {}
    else:
        _config = {
            "host": "cocohost",
            "endpoint_dir": "/etc/coco/endpoints",
            "groups": ["defgroup"],
        }

    # Merge in any test-specific config
    marker = request.node.get_closest_marker("coco_config")
    if marker is not None:
        _config = config.merge_dict_tree(_config, marker.args[0])

    # If there's no config, create nothing.
    if _config:
        # Dump it to a file
        fs.create_file("/etc/coco/coco.conf", contents=yaml.dump(_config))

        if not no_default_config:
            # Create a default endpoint, so something's there.
            fs.create_file(
                "/etc/coco/endpoints/endpoint.conf",
                contents=yaml.dump({"group": "defgroup"}),
            )


@pytest.fixture
def default_paths(fs):
    """Ensure cocod's default paths exist in the fake filesystem.

    Yields a dict containing the paths.
    """

    # Blocklist
    blocklist = "/var/lib/coco/blocklist.json"
    fs.create_file(blocklist, contents="{}")

    # storage_path
    storage_path = "/var/lib/coco/state/"
    fs.create_dir(storage_path)

    return {"blocklist": blocklist, "storage_path": storage_path}


@pytest.fixture
def cocod(coco_config, default_paths):
    """Set up coco daemon tests using click

    Yields a wrapper around click.testing.CliRunner().invoke.
    The first parameter passed to the wrapper should be
    the expected exit code.  Other parameters are passed
    to CliRunner.invoke (including the list of command
    line parameters).

    The wrapper performs rudimentary checks on the result,
    then returns the click.result so the caller can inspect
    the result further, if desired.
    """

    from click.testing import CliRunner

    # Create the runner before the test starts
    runner = CliRunner()

    def _cli_wrapper(expected_result, *args, **kwargs):
        from coco.core import cocod

        nonlocal runner

        result = runner.invoke(cocod, *args, **kwargs)

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
