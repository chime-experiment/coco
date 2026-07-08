"""Test call forwarding to other coco endpoints,"""


def test_forward(coco_runner):
    """Test that endpoints forward."""

    coco_runner.add_targets("test", 2)
    coco_runner.add_endpoint(
        "proxy",
        {
            "call": {"coco": ["end", "end2"]},
            "group": "test",
            "values": {"foo": "int", "bar": "str"},
        },
    )
    coco_runner.add_endpoint(
        "end", {"group": "test", "values": {"foo": "int", "bar": "str"}}
    )
    coco_runner.add_endpoint(
        "end2", {"group": "test", "values": {"foo": "int", "bar": "str"}}
    )

    result = coco_runner.client("end", "--foo=123", "--bar=abc", decode=True)
    assert set(result) == {"end", "queue_wait", "success"}
    assert result["success"] is True
    assert result["end"]["200"] == 2

    result = coco_runner.client("end2", "--foo=456", "--bar=def", decode=True)
    assert set(result) == {"end2", "queue_wait", "success"}
    assert result["success"] is True
    assert result["end2"]["200"] == 2

    # Now via proxy
    result = coco_runner.client("proxy", "--foo=789", "--bar=ghi", decode=True)
    assert set(result) == {"end", "end2", "proxy", "queue_wait", "success"}
    assert result["success"] is True

    # Check endpoints
    assert result["proxy"]["200"] == 2
    assert result["end"]["end"]["200"] == 2
    assert result["end"]["success"] is True
    assert result["end2"]["end2"]["200"] == 2
    assert result["end2"]["success"] is True

    # Check hits on the targets
    for target in coco_runner.targets:
        assert target.hit_count("/end") == 2
        target.assert_hit_received("/end", {"foo": 123, "bar": "abc"})
        target.assert_hit_received("/end", {"foo": 789, "bar": "ghi"})
        assert target.hit_count("/end2") == 2
        target.assert_hit_received("/end2", {"foo": 456, "bar": "def"})
        target.assert_hit_received("/end2", {"foo": 789, "bar": "ghi"})


def test_forward_tree(coco_runner):
    """Test that endpoints forward through subtrees."""

    coco_runner.add_targets("test", 2)
    coco_runner.add_endpoint(
        "proxy",
        {
            "call": {"coco": ["end/1", "end/2"]},
            "group": "test",
            "values": {"foo": "int", "bar": "str"},
        },
    )
    coco_runner.add_endpoint(
        "end/1",
        {
            "group": "test",
            "values": {"foo": "int", "bar": "str"},
            "call": {"forward": "one"},
        },
    )
    coco_runner.add_endpoint(
        "end/2",
        {
            "group": "test",
            "values": {"foo": "int", "bar": "str"},
            "call": {"forward": "two"},
        },
    )

    result = coco_runner.client("end", "1", "--foo=123", "--bar=abc", decode=True)
    assert set(result) == {"one", "queue_wait", "success"}
    assert result["success"] is True
    assert result["one"]["200"] == 2

    result = coco_runner.client("end", "2", "--foo=456", "--bar=def", decode=True)
    assert set(result) == {"two", "queue_wait", "success"}
    assert result["success"] is True
    assert result["two"]["200"] == 2

    # Now via proxy
    result = coco_runner.client("proxy", "--foo=789", "--bar=ghi", decode=True)
    assert set(result) == {"end/1", "end/2", "proxy", "queue_wait", "success"}
    assert result["success"] is True

    # Check endpoints
    assert result["proxy"]["200"] == 2
    assert result["end/1"]["one"]["200"] == 2
    assert result["end/1"]["success"] is True
    assert result["end/2"]["two"]["200"] == 2
    assert result["end/2"]["success"] is True

    # Check hits on the targets
    for target in coco_runner.targets:
        assert target.hit_count("/one") == 2
        target.assert_hit_received("/one", {"foo": 123, "bar": "abc"})
        target.assert_hit_received("/one", {"foo": 789, "bar": "ghi"})
        assert target.hit_count("/two") == 2
        target.assert_hit_received("/two", {"foo": 456, "bar": "def"})
        target.assert_hit_received("/two", {"foo": 789, "bar": "ghi"})
