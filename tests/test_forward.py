"""Test basic endpoint call forwarding."""

import pytest


@pytest.fixture
def runner(coco_runner):
    """coco_runner with pre-made endpoint.

    (And targets)
    """

    coco_runner.add_targets("test", 2)
    coco_runner.add_endpoint(
        "test",
        {
            "group": "test",
            "report_latency": True,
            "values": {"foo": "int", "bar": "str"},
        },
    )
    return coco_runner


def test_forward(runner):
    """Test if a request gets forwarded to an external endpoint."""
    request = {"foo": 0, "bar": "1337"}
    response = runner.client("-r", "FULL", "test", "--foo=0", "--bar=1337", decode=True)

    assert "test" in response
    for t in runner.targets:
        assert t.hit_count("/test") == 1
        h = f"http://127.0.0.1:{t.port}/"
        assert h in response["test"]
        assert "status" in response["test"][h]
        assert "reply" in response["test"][h]

        assert response["test"][h]["status"] == 200
        assert response["test"][h]["reply"]["body"] == request

    runner.client("test", "--foo=0", "--bar=1337")
    runner.client("test", "--foo=0", "--bar=1337")
    for t in runner.targets:
        assert t.hit_count("/test") == 3


def test_wrong_vars(runner):
    request = {"foo": "dfg", "bar": 1337}
    response, _ = runner.call_endpoint("test", data=request)
    assert response.status == 400

    request = {"foo": 1337}
    response, _ = runner.call_endpoint("test", data=request)
    assert response.status == 400


def test_url_args(runner):
    """Test if URL arguments get forwarded to an external endpoint."""

    request = {"foo": 0, "bar": "1337"}
    request_full = request.copy()
    request_full.update({"coco_report_type": "FULL"})
    params = {"cat": "1", "hat": "rat"}
    query_str = "&".join([f"{k}={params[k]}" for k in params])

    response, json = runner.call_endpoint("test", data=request_full, query=query_str)
    assert response.status == 200

    assert "test" in json
    for t in runner.targets:
        h = f"http://127.0.0.1:{t.port}/"
        assert h in json["test"]
        assert "status" in json["test"][h]
        assert "reply" in json["test"][h]
        assert "query" in json["test"][h]["reply"]
        assert (
            "latency" in json["test"][h]
        )  # Check that per-host latencies are returned

        assert json["test"][h]["status"] == 200
        assert json["test"][h]["reply"] == {
            "body": request,
            "path": "/test",
            "query": query_str,
            "result": "success",
        }


def test_latency_stats(runner):
    """Test if latency stats are returned from external endpoint"""

    response = runner.client("test", "--foo=0", "--bar=1337", decode=True)
    assert "latency_stats" in response["test"]
