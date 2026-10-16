"""Test prometheus metrics collection."""

import statistics
from time import sleep

from prometheus_client.parser import text_string_to_metric_families

from coco.core import all_local_endpoints


def test_metrics(coco_runner):
    coco_runner.add_targets("test", 2)
    targets = coco_runner.targets

    coco_runner.add_endpoint(
        "status",
        {
            "call": {"forward": "status-host"},
            "group": "test",
            "values": {"foo": "int", "bar": "str"},
        },
    )

    N_CALLS = 3
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
    all_blocklisted = []
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
            elif sample.name == "coco_blocklisted":
                all_blocklisted.append(
                    (sample.labels["host"], sample.labels["port"], sample.value)
                )

    # Expect one endpoint plus all the internal local endpoints
    assert len(all_dropped) == len(all_local_endpoints) + 1

    assert list(status_dropped.labels.keys()) == ["endpoint"]
    # No requests should have been dropped
    assert status_dropped.value == 0

    # Expect one sample per host per endpoint
    assert len(all_forward) == len(targets)
    for s in all_forward:
        assert set(s.labels.keys()) == {"endpoint", "host", "port", "status"}

    # Expect only queue wait time for "status", because that's all the test calls
    assert len(all_wait_time) == 1

    # Also have observations of the histograms
    assert all_wait_time["status"].value == N_CALLS
    assert all_response_time["status-host"].value == N_CALLS

    # All targets are present in the blocklist, but none of them are blocked.
    assert len(all_blocklisted) == len(targets)
    for target in targets:
        assert ("127.0.0.1", str(target.port), 0) in all_blocklisted


def test_blocklisted_metric(coco_runner):
    """Test the coco_blocklisted metric."""

    def _blocklist_from_metrics(coco_runner):
        """Extracts the blocklist from the metrics."""

        # Anti-race-condition wait
        sleep(0.1)

        # Get metrics
        result, metrics = coco_runner.call_endpoint("metrics")
        assert result.status == 200
        blocklist = {}

        # Parse metrics
        metrics = text_string_to_metric_families(metrics)
        for metric in metrics:
            for sample in metric.samples:
                if sample.name == "coco_blocklisted":
                    # In this test case, the "host" label is always localhost
                    # so we can ignore it
                    blocklist[int(sample.labels["port"])] = sample.value

        return blocklist

    # Create some targets for the blocklist to use
    coco_runner.add_targets("test", 5)

    # A set of target ports
    targets = {target.port for target in coco_runner.targets}

    # Start the daemon
    coco_runner.start_daemon()

    # Check the reported blocklist
    blocklist = _blocklist_from_metrics(coco_runner)
    assert len(blocklist) == len(targets)
    for target in targets:
        assert target in blocklist
        assert blocklist[target] == 0

    # Blocklist all targets below the median target
    median = statistics.median(targets)
    coco_runner.call_endpoint(
        "update-blocklist",
        method="POST",
        data={
            "command": "add",
            "hosts": [f"127.0.0.1:{port}" for port in targets if port < median],
        },
    )

    # Check the reported blocklist
    blocklist = _blocklist_from_metrics(coco_runner)
    assert len(blocklist) == len(targets)
    for target in targets:
        assert target in blocklist
        assert blocklist[target] == (1 if target < median else 0)

    # Un-blocklist the lowest target
    least = min(targets)
    coco_runner.call_endpoint(
        "update-blocklist",
        method="POST",
        data={"command": "remove", "hosts": [f"127.0.0.1:{least}"]},
    )

    # Check the reported blocklist
    blocklist = _blocklist_from_metrics(coco_runner)
    assert len(blocklist) == len(targets)
    for target in targets:
        assert target in blocklist
        if target == least:
            assert blocklist[target] == 0
        else:
            assert blocklist[target] == (1 if target < median else 0)
