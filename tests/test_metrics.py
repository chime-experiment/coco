"""Test prometheus metrics collection."""

from prometheus_client.parser import text_string_to_metric_families

from coco.core import all_local_endpoints


def test_metrics(coco_runner):
    coco_runner.add_targets("test", 2)
    coco_runner.add_endpoint(
        "status",
        {
            "call": {"forward": "status-host"},
            "group": "test",
            "values": {"foo": "int", "bar": "str"},
        },
    )

    N_CALLS = 2
    for i in range(N_CALLS):
        coco_runner.client("status", "--foo=0", "--bar=1337")

    # Get metrics
    result, metrics = coco_runner.call_endpoint("metrics")
    assert result.status == 200
    metrics = text_string_to_metric_families(metrics)

    # parse metrics
    all_dropped = []
    status_dropped = None
    all_forward = []
    all_wait_time = {}
    all_response_time = {}
    for metric in metrics:
        for sample in metric.samples:
            if sample.name == "coco_dropped_request_total":
                all_dropped.append(sample)
                if sample.labels["endpoint"] == "status":
                    status_dropped = sample
            elif sample.name == "coco_calls_total":
                all_forward.append(sample)
            elif sample.name == "coco_queue_wait_time_seconds_count":
                all_wait_time[sample.labels["endpoint"]] = sample
            elif sample.name == "coco_external_response_time_seconds_count":
                all_response_time[sample.labels["endpoint"]] = sample

    # Expect one endpoint plus all the internal local endpoints
    assert len(all_dropped) == len(all_local_endpoints) + 1

    assert list(status_dropped.labels.keys()) == ["endpoint"]
    # No requests should have been dropped
    assert status_dropped.value == 0

    # Expect one sample per host per endpoint
    assert len(all_forward) == 2
    for s in all_forward:
        assert set(s.labels.keys()) == {"endpoint", "host", "port", "status"}

    # Expect only queue wait time for "status", because that's all the test calls
    assert len(all_wait_time) == 1

    # Also have observations of the histograms
    assert all_wait_time["status"].value == 2
    assert all_response_time["status-host"].value == 2
