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
