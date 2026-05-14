"""Test coco/config.py"""

import click
import pytest
import yaml

from coco import config


@pytest.mark.no_default_config(True)
def test_no_config(coco_config):
    """No config causes an error."""
    with pytest.raises(click.ClickException):
        config.load_config()


@pytest.mark.no_default_config(True)
def test_missing_required(coco_config):
    """Test reporting missing required config."""

    # Because of the "no_default_config" mark above, the only config
    # that we have will be this.  (We need to write something to
    # the config file for the test fixutre to create it.)
    coco_config({"test": "test"})

    with pytest.raises(click.ClickException) as exinfo:
        config.load_config()

    # Run through the skeleton and make sure everything is reported
    for name, val in config._config_skeleton.items():
        if val is config.RequiredValue:
            assert name in exinfo.value.args[0]


def test_config_path(fs, coco_config):
    """Test that a path passed in to load_config is loaded."""

    # Create a test file
    fs.create_file("/test/test.conf", contents=yaml.dump({"host": "canary"}))

    result = config.load_config("/test/test.conf")
    assert result["host"] == "canary"


def test_config_envar(fs, monkeypatch, coco_config):
    """Test that a path passed in via envar loaded."""

    # Create a test file
    fs.create_file("/test/test.conf", contents=yaml.dump({"host": "canary"}))

    monkeypatch.setenv("COCO_CONFIG_FILE", "/test/test.conf")
    result = config.load_config()
    assert result["host"] == "canary"


def test_config_ordering(fs, monkeypatch, coco_config):
    """A passed-in path supercedes everything else."""

    # Create some test file
    fs.create_file(
        "/test/envar.conf", contents=yaml.dump({"host": "envar", "envar_seen": True})
    )
    fs.create_file(
        "/test/cmdline.conf",
        contents=yaml.dump({"host": "cmdline", "cmdline_seen": True}),
    )

    monkeypatch.setenv("COCO_CONFIG_FILE", "/test/envar.conf")
    result = config.load_config("/test/cmdline.conf")
    assert result["host"] == "cmdline"
    assert "envar_seen" in result
    assert "cmdline_seen" in result


def test_missing_files(monkeypatch, coco_config):
    """User-specified config files must exist."""

    with pytest.raises(click.ClickException):
        config.load_config("/missing/file")

    monkeypatch.setenv("COCO_CONFIG_FILE", "/missing/file")
    with pytest.raises(click.ClickException):
        config.load_config()


def test_default_config(coco_config):
    """Loading the default test config should work."""
    result = config.load_config()

    from conftest import DEFAULT_TEST_CONFIG

    # Result should be the test default merged with coco's default
    expected_result = config.merge_dict_tree(
        config._config_skeleton, DEFAULT_TEST_CONFIG
    )

    # But also the default endpoint
    expected_result = config.merge_dict_tree(
        expected_result, {"endpoints": [{"group": "defgroup", "name": "endpoint"}]}
    )

    assert result == expected_result


def test_utf8_error(fs, coco_config):
    """Try loading a non-UTF-8 config file."""

    # This contains a UTF-16 surrogate, U+D801, encoded in UTF-8 to the
    # forbidden byte sequence ED A0 81
    fs.create_file("/test/test.conf", contents=b"---\nhost: \xed\xa0\x81\n")

    with pytest.raises(click.ClickException):
        config.load_config("/test/test.conf")


def test_yaml_error(fs, coco_config):
    """Test reading a non-YAML config file"""
    fs.create_file("/test/test.conf", contents="a: b: c:\n")

    with pytest.raises(click.ClickException):
        config.load_config("/test/test.conf")


def test_no_map(fs, coco_config):
    """Test reading a non-mapping YAML config file"""
    fs.create_file("/test/test.conf", contents="---\njust_a_scalar\n")

    with pytest.raises(click.ClickException):
        config.load_config("/test/test.conf")


def test_endpoint_skipping(fs, coco_config):
    """Test skipped files in the endpoint dir."""

    # This is skipped because it doesn't end in ".conf"
    fs.create_file(
        "/etc/coco/endpoints/no_conf.yaml", contents=yaml.dump({"group": "defgroup"})
    )

    # This is skipped because endpoints with a leading _ are disabled.
    fs.create_file(
        "/etc/coco/endpoints/_disabled.conf", contents=yaml.dump({"group": "defgroup"})
    )

    # This one should work
    fs.create_file(
        "/etc/coco/endpoints/check.conf", contents=yaml.dump({"group": "defgroup"})
    )

    result = config.load_config()

    # The only endpoints should be "check" and the fixture-created "endpoint"
    assert len(result["endpoints"]) == 2
    assert {endpoint["name"] for endpoint in result["endpoints"]} == {
        "check",
        "endpoint",
    }


def test_utf8_endpoint_error(fs, coco_config):
    """Try loading a non-UTF-8 endpoint."""

    # This contains a UTF-16 surrogate, U+D801, encoded in UTF-8 to the
    # forbidden byte sequence ED A0 81
    fs.create_file(
        "/etc/coco/endpoints/test.conf", contents=b"---\ngroup: \xed\xa0\x81\n"
    )

    with pytest.raises(click.ClickException):
        config.load_config()


def test_yaml_endpoint_error(fs, coco_config):
    """Test reading a non-YAML endpoint"""
    fs.create_file("/etc/coco/endpoints/test.conf", contents="a: b: c\n")

    with pytest.raises(click.ClickException):
        config.load_config()


def test_no_map_endpoing(fs, coco_config):
    """Test reading a non-mapping YAML endpoint"""
    fs.create_file("/etc/coco/endpoints/test.conf", contents="---\njust_a_scalar\n")

    with pytest.raises(click.ClickException):
        config.load_config()


def test_str_keys(coco_config):
    """All config keys are strings."""

    # Update config
    coco_config({1234: "test", "subdict": {5.6: "test"}, "dictlist": [{True: "test"}]})

    result = config.load_config()

    assert "1234" in result
    assert 1234 not in result
    assert "5.6" in result["subdict"]
    assert 5.6 not in result["subdict"]
    assert "True" in result["dictlist"][0]
    assert True not in result["dictlist"][0]
