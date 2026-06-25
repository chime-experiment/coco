"Test the test fixtures"


def test_runner(coco_runner):
    """Test coco runner.

    This tests the coco runner fixture to make sure it can start up and shut
    down cleanly.  This is not a test of the production code."""
    coco_runner.start_daemon()
    result = coco_runner.stop()
    assert result["exit_code"] == 0
