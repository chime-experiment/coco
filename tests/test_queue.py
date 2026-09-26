"""Redis queue tests."""

from prometheus_client.parser import text_string_to_metric_families


def test_limited_queue(coco_runner):
    """Test limited queue length."""
    QUEUE_LEN = 3

    coco_runner.add_config(queue_length=QUEUE_LEN)
    coco_runner.add_targets("test", 1)
    coco_runner.add_endpoint(
        "do_wait",
        {
            "group": "test",
            "call": {"coco": {"name": "wait", "request": {"duration": "3s"}}},
        },
    )
    coco_runner.add_endpoint("test", {"group": "test"})

    # Block the qworker
    coco_runner.enqueue("do_wait")

    # Fill up the queue (the qworker has already popped the do_wait)
    for _ in range(QUEUE_LEN):
        coco_runner.enqueue("test")

    # Queue now full
    result, _ = coco_runner.call_endpoint("test")
    assert result.status == 503

    # Check metrics record dropped requests
    result, metrics = coco_runner.call_endpoint("metrics")
    assert result.status == 200

    metrics = text_string_to_metric_families(metrics)
    # parse metrics
    count_coco = []
    for metric in metrics:
        for sample in metric.samples:
            if sample.name == "coco_dropped_request_total":
                count_coco.append(sample)

    # Find test endpoint metric
    missing = True
    for sample in count_coco:
        if sample.labels["endpoint"] == "test":
            assert sample.value == 1.0
            missing = False
    assert not missing
