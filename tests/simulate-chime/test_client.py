"""
coco-client tests that assume coco and kotekan is running (use run_test.sh). This really tests the
endpoint configuration files used by CHIME.
"""

import orjson as json
import time
import subprocess

client_args = [
    "./coco-client",
    "-s",
    "json",
    "-c",
    "../tests/simulate-chime/coco.conf",
    "-r",
    "FULL",
]
NUM_NODES = 10


def test_client():
    result = subprocess.check_output(client_args + ["start"], encoding="utf-8")
    result = json.loads(result)
    assert isinstance(result, dict)
    assert "version" in result
    assert "version" in result["version"]
    assert "status" in result
    assert "status" in result["status"]
    assert "start-receiver" in result
    assert "start-cluster" in result
    assert "start" in result["start-receiver"]
    assert "start" in result["start-cluster"]

    assert len(result["version"]["version"].keys()) == NUM_NODES
    reply = None
    for n in result["version"]["version"].values():
        assert n["status"] == 200
        if reply:
            assert n["reply"] == reply
            reply = n["reply"]

    for n in result["status"]["status"].values():
        assert n["status"] == 200
        assert n["reply"] == {"running": True}

    for n in result["start-cluster"]["start"].values():
        assert n["status"] == 200
        assert n["reply"] == None

    for n in result["start-receiver"]["start"].values():
        assert n["status"] == 200
        assert n["reply"] == None

    # Give kotekan some time to start
    time.sleep(5)

    # Starting again should fail
    result = subprocess.check_output(client_args + ["start"], encoding="utf-8")
    result = json.loads(result)
    assert isinstance(result, dict)
    assert "version" in result
    assert "version" in result["version"]
    assert "status" in result
    assert "status" in result["status"]
    assert "start-receiver" in result
    assert "start-cluster" in result
    assert "start" in result["start-receiver"]
    assert "start" in result["start-cluster"]

    assert len(result["version"]["version"].keys()) == NUM_NODES
    reply = None
    for n in result["version"]["version"].values():
        assert n["status"] == 200
        if reply:
            assert n["reply"] == reply
            reply = n["reply"]

    for n in result["status"]["status"].values():
        assert n["status"] == 200
        assert n["reply"] == {"running": True}

    for n in result["start-cluster"]["start"].values():
        assert n["status"] == 402
        assert n["reply"] == {"code": 402, "message": "Already running"}

    for n in result["start-receiver"]["start"].values():
        assert n["status"] == 402
        assert n["reply"] == {"code": 402, "message": "Already running"}

    # Call some endpoints
    result = subprocess.check_output(client_args + ["status"], encoding="utf-8")
    result = json.loads(result)
    assert isinstance(result, dict)
    assert "status" in result
    for n in result["status"].values():
        assert n["status"] == 200
        assert n["reply"] == {"running": True}

    # Update pulsar gating
    result = subprocess.check_output(
        client_args
        + [
            "update-pulsar-gating",
            "True",
            "fake_pulsar",
            "1.0",
            "1.0",
            "[1.0]",
            "[1.0]",
            "1.0",
            "1.0",
            "[[1.0]]",
        ],
        encoding="utf-8",
    )
    result = json.loads(result)
    assert isinstance(result, dict)
    assert "updatable_config/gating/psr0_config" in result
    for n in result["updatable_config/gating/psr0_config"].values():
        assert n["status"] == 200

    # Update pulsar pointing
    # Test disabled until changed in kotekan (https://github.com/kotekan/kotekan/pull/431)
    # for i in range(10):
    #     result = subprocess.check_output(
    #         client_args + [f"update-pulsar-pointing-{i}", f"{0.1 * i}", f"{0.2 * i}", f"{i}"],
    #         encoding="utf-8",
    #     )
    #     result = json.loads(result)
    #     assert isinstance(result, dict)
    #     assert f"updatable_config/pulsar_pointing/{i}" in result
    #     for n in result[f"updatable_config/pulsar_pointing/{i}"].values():
    #         assert n["status"] == 200

    # Update east west beam
    for i in range(4):
        result = subprocess.check_output(
            client_args + [f"update-east-west-beam-{i}", f"{i}", f"{0.1 * i}"], encoding="utf-8"
        )
        result = json.loads(result)
        assert isinstance(result, dict)
        assert f"gpu/gpu_{i}/frb/update_EW_beam/{i}" in result
        print(result)
        for n in result[f"gpu/gpu_{i}/frb/update_EW_beam/{i}"].values():
            assert n["status"] == 200

    # Update north south beam
    result = subprocess.check_output(
        client_args + ["update-north-south-beam", "1.0"], encoding="utf-8"
    )
    result = json.loads(result)
    assert isinstance(result, dict)
    for i in range(4):
        assert f"gpu/gpu_{i}/frb/update_NS_beam/{i}" in result
        for n in result[f"gpu/gpu_{i}/frb/update_NS_beam/{i}"].values():
            assert n["status"] == 200

    # Update beam offset
    result = subprocess.check_output(
        client_args + ["update-beam-offset", "1"], encoding="utf-8"
    )
    result = json.loads(result)
    assert isinstance(result, dict)
    assert f"frb/update_beam_offset" in result
    for n in result[f"frb/update_beam_offset"].values():
        assert n["status"] == 200

    # Update bad inputs
    result = subprocess.check_output(
        client_args + ["update-bad-inputs", "fake_flagging", "1562790762.70961", "[]"],
        encoding="utf-8",
    )
    result = json.loads(result)
    assert isinstance(result, dict)
    assert f"updatable_config/flagging" in result
    for n in result[f"updatable_config/flagging"].values():
        assert n["status"] == 200

    # TODO: check if config changed all the parameters

    result = subprocess.check_output(client_args + ["stop"], encoding="utf-8")
    result = json.loads(result)
    assert isinstance(result, dict)
    assert "stop-cluster" in result
    assert "stop-receiver" in result
    assert "kill" in result["stop-cluster"]
    assert "kill" in result["stop-receiver"]
    for n in result["stop-cluster"]["kill"].values():
        assert n["status"] == 200
        assert n["reply"] is None

    for n in result["stop-receiver"]["kill"].values():
        assert n["status"] == 200
        assert n["reply"] is None
