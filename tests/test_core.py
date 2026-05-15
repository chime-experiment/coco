"""Test the coco daemon (coco.core)."""

import pytest

import coco.core


def test_help(cocod):
    """Test cocod --help"""

    result = cocod(0, ["--help"])
    assert coco.core.cocod.__doc__ in result.output


@pytest.mark.coco_config({"log_level": "INVALID"})
def test_bad_log_level(cocod):
    """Try invalid log_level."""

    result = cocod(1)
    assert "INVALID" in result.output


@pytest.mark.coco_config({"blocklist_path": "invalid_blocklist_path"})
def test_relative_blocklist_path(cocod):
    """blocklist_path must be absolute"""

    result = cocod(1)
    assert "invalid_blocklist_path" in result.output


@pytest.mark.coco_config({"storage_path": "invalid_storage_path"})
def test_relative_storage_path(cocod):
    """storage_path must be absolute"""

    result = cocod(1)
    assert "invalid_storage_path" in result.output


@pytest.mark.coco_config({"storage_path": "/storage/path"})
def test_storage_missing(fs, cocod):
    """storage_path must exist"""

    result = cocod(1)
    assert "/storage/path" in result.output


@pytest.mark.coco_config({"storage_path": "/storage/path"})
def test_storage_path_not_dir(fs, cocod):
    """storage_path must be a directory"""

    # Create a file at the storage_path
    fs.create_file("/storage/path", contents="")
    result = cocod(1)
    assert "/storage/path" in result.output


@pytest.mark.coco_config({"groups": ["group1", "group2"]})
def test_groups_not_map(fs, cocod):
    """The "groups" config must be a dict of lists."""

    result = cocod(1)
    assert "groups" in result.output


@pytest.mark.coco_config({"groups": {"group1": "scalar"}})
def test_groups_not_list(fs, cocod):
    """The "groups" config must ce a dict of lists."""

    result = cocod(1)
    assert "groups" in result.output


@pytest.mark.coco_config({"groups": {"group1": [":1234"]}})
def test_groups_bad_host(fs, cocod):
    """Test catching bad hosts in groups lists."""

    result = cocod(1)
    assert ":1234" in result.output


@pytest.mark.coco_config({"slack_rules": [{"logger": "logger"}]})
def test_slack_rules_no_channel(fs, cocod):
    """Slack rules must contain a "channel" key."""

    result = cocod(1)
    assert "channel" in result.output


@pytest.mark.coco_config({"slack_rules": [{"channel": "channel"}]})
def test_slack_rules_no_logger(fs, cocod):
    """Slack rules must contain a "logger" key."""

    result = cocod(1)
    assert "logger" in result.output


@pytest.mark.coco_config({"comet_broker": {"enabled": False}})
def test_reset(fs, default_paths, cocod):
    """Check --reset works."""

    # Current state
    storage_path = default_paths["storage_path"]
    fs.create_file(f"{storage_path}/active", contents='{"key": "value"}')

    # --check-config ensures the daemon exits after the test.
    cocod(0, ["--reset", "--check-config"])


@pytest.mark.coco_config({"comet_broker": {"enabled": False}})
def test_full_reset(fs, default_paths, cocod):
    """Check --full-reset works."""

    # Current state file can be invalid in this case
    storage_path = default_paths["storage_path"]
    fs.create_file(f"{storage_path}/active", contents="{{{{{{")

    # --check-config ensures the daemon exits after the test.
    cocod(0, ["--full-reset", "--check-config"])
