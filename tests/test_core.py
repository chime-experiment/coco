"""Test the coco daemon (coco.core)."""

import coco.core


def test_help(cocod):
    """Test cocod --help"""

    result = cocod(0, ["--help"])
    assert coco.core.cocod.__doc__ in result.output


def test_bad_log_level(cocod, coco_config):
    """Try invalid log_level."""

    coco_config({"log_level": "INVALID"})

    result = cocod(1)
    assert "INVALID" in result.output


def test_relative_blocklist_path(cocod, coco_config):
    """blocklist_path must be absolute"""

    coco_config({"blocklist_path": "invalid_blocklist_path"})

    result = cocod(1)
    assert "invalid_blocklist_path" in result.output


def test_relative_storage_path(cocod, coco_config):
    """storage_path must be absolute"""

    coco_config({"storage_path": "invalid_storage_path"})

    result = cocod(1)
    assert "invalid_storage_path" in result.output


def test_storage_missing(fs, cocod, coco_config):
    """storage_path must exist"""

    coco_config({"storage_path": "/storage/path"})

    result = cocod(1)
    assert "/storage/path" in result.output


def test_storage_path_not_dir(fs, cocod, coco_config):
    """storage_path must be a directory"""

    coco_config({"storage_path": "/storage/path"})

    # Create a file at the storage_path
    fs.create_file("/storage/path", contents="")
    result = cocod(1)
    assert "/storage/path" in result.output


def test_groups_not_map(fs, cocod, coco_config):
    """The "groups" config must be a dict of lists."""

    coco_config({"groups": ["group1", "group2"]})

    result = cocod(1)
    assert "groups" in result.output


def test_groups_not_list(fs, cocod, coco_config):
    """The "groups" config must ce a dict of lists."""

    coco_config({"groups": {"group1": "scalar"}})

    result = cocod(1)
    assert "groups" in result.output


def test_groups_bad_host(fs, cocod, coco_config):
    """Test catching bad hosts in groups lists."""

    coco_config({"groups": {"group1": [":1234"]}})

    result = cocod(1)
    assert ":1234" in result.output


def test_slack_rules_no_channel(fs, cocod, coco_config):
    """Slack rules must contain a "channel" key."""

    coco_config({"slack_rules": [{"logger": "logger"}]})

    result = cocod(1)
    assert "channel" in result.output


def test_slack_rules_no_logger(fs, cocod, coco_config):
    """Slack rules must contain a "logger" key."""

    coco_config({"slack_rules": [{"channel": "channel"}]})

    result = cocod(1)
    assert "logger" in result.output


def test_reset(fs, storage_path, cocod):
    """Check --reset works."""

    # Current state
    fs.create_file(f"{storage_path}/active", contents='{"key": "value"}')

    # --check-config ensures the daemon exits after the test.
    cocod(0, ["--reset", "--check-config"])


def test_full_reset(fs, storage_path, cocod):
    """Check --full-reset works."""

    # Current state file can be invalid in this case
    fs.create_file(f"{storage_path}/active", contents="{{{{{{")

    # --check-config ensures the daemon exits after the test.
    cocod(0, ["--full-reset", "--check-config"])


def test_comet(mock_comet, coco_runner):
    """Ensure coco registers start-up with comet."""

    from coco import __version__

    # Configure comet in the coco_runner
    coco_runner.add_config(
        comet_broker={"enabled": True, "host": "127.0.0.1", "port": mock_comet.port}
    )

    # Start the daemon
    coco_runner.start_daemon()

    # Check that everything was registered.  The counts are 2 here
    # because the "start" state is separate from the "config" state.
    assert mock_comet.hit_count("/register-state") == 2
    assert mock_comet.hit_count("/send-state") == 2

    # Check the coco config was sent
    mock_comet.assert_hit_received(
        "/send-state",
        {"state": {"version": __version__, "config_state": coco_runner.config}},
    )

    # Check for no error from daemon
    coco_runner.stop()


def test_comet_check_config(mock_comet, coco_runner):
    """Test that "cocod --check-config" doesn't invoke comet.

    We don't want cocod registering its start in this case.
    """

    # Configure comet in the coco_runner
    coco_runner.add_config(
        comet_broker={"enabled": True, "host": "127.0.0.1", "port": mock_comet.port}
    )

    # Start the daemon
    coco_runner.start_daemon("--check-config")

    # Check that comet wasn't called.
    assert mock_comet.hit_count("/register-state") == 0
    assert mock_comet.hit_count("/send-state") == 0

    # Check for no error from daemon
    coco_runner.stop()
