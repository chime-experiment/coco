"""Test endpoint scheduler."""

import time

import yaml


def test_sched(coco_runner):
    """Test if scheduled endpoints are called when they should be."""
    PERIOD = 0.5

    coco_runner.add_targets("test", 2, callback=lambda path, data: data)
    coco_runner.add_endpoint(
        "scheduled", {"group": "test", "schedule": {"period": PERIOD}}
    )
    coco_runner.add_endpoint(
        "scheduled-check-type",
        {
            "group": "test",
            "schedule": {
                "period": PERIOD,
                "require_state": {"path": "test/success", "type": "bool"},
            },
        },
    )
    coco_runner.add_endpoint(
        "scheduled-check-val",
        {
            "group": "test",
            "schedule": {
                "period": PERIOD,
                "require_state": {
                    "path": "test/success",
                    "type": "bool",
                    "value": True,
                },
            },
        },
    )
    coco_runner.add_endpoint(
        "scheduled-fail-type",
        {
            "group": "test",
            "schedule": {
                "period": PERIOD,
                "require_state": {"path": "test/fail_type", "type": "bool"},
            },
        },
    )
    coco_runner.add_endpoint(
        "scheduled-fail-val",
        {
            "group": "test",
            "schedule": {
                "period": PERIOD,
                "require_state": {
                    "path": "test/fail_val",
                    "type": "bool",
                    "value": True,
                },
            },
        },
    )

    # This is not a state file, but we'll throw it into the storage_path, just because
    # it's a convenient place to put it.
    with open(coco_runner.storage_path / "TEST.yaml", "w") as f:
        yaml.dump({"success": True, "fail_type": "not_a_bool", "fail_val": False}, f)
    coco_runner.add_config(
        load_state={"test": str(coco_runner.storage_path / "TEST.yaml")}
    )

    coco_runner.start_daemon()
    # Let at least three periods pass
    time.sleep(3.5 * PERIOD)
    coco_runner.stop()

    for t in coco_runner.targets:
        # We don't know this precisely, because more periods may
        # happen during the coco_runner daemon set-up and teardown
        assert t.hit_count("/scheduled") >= 3
        num_sched = t.hit_count("/scheduled")
        assert t.hit_count("/scheduled-check-type") == num_sched
        assert t.hit_count("/scheduled-check-val") == num_sched
        assert t.hit_count("/scheduled-fail-type") == 0
        assert t.hit_count("/scheduled-fail-val") == 0
