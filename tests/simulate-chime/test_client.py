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
    result = subprocess.check_output(client_args + ["update-beam-offset", "10"], encoding="utf-8")
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

    # Update gains
    result = subprocess.check_output(
        client_args + ["update-gain", "update_gain", "1562790762.70962"], encoding="utf-8"
    )
    result = json.loads(result)
    assert isinstance(result, dict)
    assert f"updatable_config/gains" in result
    for n in result[f"updatable_config/gains"].values():
        assert n["status"] == 200

    # Update frb gain dir
    result = subprocess.check_output(
        client_args + ["update-frb-gain-dir", "insert/sth/useful"], encoding="utf-8"
    )
    result = json.loads(result)
    assert isinstance(result, dict)
    assert f"frb_gain" in result
    for n in result[f"frb_gain"].values():
        assert n["status"] == 200

    # Update pulsar gain dir
    result = subprocess.check_output(
        client_args + ["update-pulsar-gain-dirs", '["insert/sth/useful"]'], encoding="utf-8"
    )
    result = json.loads(result)
    assert isinstance(result, dict)
    assert f"pulsar_gain" in result
    for n in result[f"pulsar_gain"].values():
        assert n["status"] == 200

    # check if config changed all the parameters
    result = subprocess.check_output(client_args + ["kotekan-running-config"], encoding="utf-8")
    result = json.loads(result)
    assert isinstance(result, dict)
    assert f"config" in result
    for n in result[f"config"].values():
        assert n["status"] == 200
        conf = n["reply"]

        # check pulsar gating in config
        assert conf["updatable_config"]["gating"]["psr0_config"] == {
            "enabled": True,
            "pulsar_name": "fake_pulsar",
            "pulse_width": 1.0,
            "rot_freq": 1.0,
            "phase_ref": [1.0],
            "t_ref": [1.0],
            "segment": 1.0,
            "dm": 1.0,
            "coeff": [[1.0]],
            "kotekan_update_endpoint": "json",
        }
        # check east west beam in config
        for i in range(4):
            assert conf["gpu"][f"gpu_{i}"]["frb"]["update_EW_beam"][f"{i}"] == {
                "ew_id": i,
                "ew_beam": 0.1 * i,
                "kotekan_update_endpoint": "json",
            }

        # check north south beam in config
        for i in range(4):
            assert (
                conf["gpu"][f"gpu_{i}"]["frb"]["update_NS_beam"][f"{i}"]["northmost_beam"] == 1.0
            )

        # check beam offset in config
        assert conf["frb"]["update_beam_offset"]["beam_offset"] == 10

        # check frb gain dir in config
        assert conf["frb_gain"]["frb_gain_dir"] == "insert/sth/useful"

        # check pulsar gain dir in config
        assert conf["pulsar_gain"]["pulsar_gain_dir"] == ["insert/sth/useful"]

    # TODO: check receiver config: bad inputs, gains
    # TODO check status: timestamp of frb-gain-dir

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
