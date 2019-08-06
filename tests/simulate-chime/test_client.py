"""
coco-client tests that assume coco and kotekan is running (use run_test.sh). This really tests the
endpoint configuration files used by CHIME.
"""

import orjson as json
import time
import subprocess
import requests

client_args = ["./coco", "-s", "json", "-c", "../tests/simulate-chime/coco.conf", "-r", "FULL"]
NUM_NODES = 10


def test_client():
    result = subprocess.check_output(client_args + ["start"], encoding="utf-8")
    result = json.loads(result)
    assert isinstance(result, dict)
    assert "version-cluster" in result
    assert "version" in result["version-cluster"]
    assert "status-cluster" in result
    assert "status" in result["status-cluster"]
    assert "start-receiver" in result
    assert "start-cluster" in result
    assert "start" in result["start-receiver"]
    assert "start" in result["start-cluster"]

    assert len(result["version-cluster"]["version"].keys()) == NUM_NODES
    reply = None
    for n in result["version-cluster"]["version"].values():
        assert n["status"] == 200
        if reply:
            assert n["reply"] == reply
            reply = n["reply"]

    for n in result["status-cluster"]["status"].values():
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
    assert "version-cluster" in result
    assert "version" in result["version-cluster"]
    assert "status-cluster" in result
    assert "status" in result["status-cluster"]
    assert "start-receiver" in result
    assert "start-cluster" in result
    assert "start" in result["start-receiver"]
    assert "start" in result["start-cluster"]

    assert len(result["version-cluster"]["version"].keys()) == NUM_NODES
    reply = None
    for n in result["version-cluster"]["version"].values():
        assert n["status"] == 200
        if reply:
            assert n["reply"] == reply
            reply = n["reply"]

    for n in result["status-cluster"]["status"].values():
        assert n["status"] == 200
        assert n["reply"] == {"running": True}

    for n in result["start-cluster"]["start"].values():
        assert n["status"] == 402
        assert n["reply"] == {"code": 402, "message": "Already running"}

    for n in result["start-receiver"]["start"].values():
        assert n["status"] == 402
        assert n["reply"] == {"code": 402, "message": "Already running"}

    # Check config hash
    result = subprocess.check_output(client_args + ["kotekan_config_md5sum"], encoding="utf-8")
    assert "config_md5sum" in result
    assert "failed_checks" not in result

    print("TEST: Config hash matches after start.")

    # Call some endpoints
    result = subprocess.check_output(client_args + ["status-cluster"], encoding="utf-8")
    result = json.loads(result)
    assert isinstance(result, dict)
    assert "status" in result
    for n in result["status"].values():
        assert n["status"] == 200
        assert n["reply"] == {"running": True}

    # Check config hash
    result = subprocess.check_output(client_args + ["kotekan_config_md5sum"], encoding="utf-8")
    assert "config_md5sum" in result
    assert "failed_checks" not in result

    print("TEST: Config hash matches after calling status-cluster.")

    # Update pulsar gating
    result = subprocess.check_output(
        client_args
        + [
            "update-pulsar-gating",  # endpoint name
            "True",  # enabled
            "fake_pulsar",  # pulsar name
            "1e-3",  # pulse_width
            "0.03e3",  # rot_freq
            "[0.]",  # phase_ref
            "[58000.]",  # t_ref
            "0.",  # segment
            "0.",  # dm
            "[[0., 0.]]",  # coeff
        ],
        encoding="utf-8",
    )
    result = json.loads(result)
    assert isinstance(result, dict)
    assert "updatable_config/gating/psr0_config" in result
    for n in result["updatable_config/gating/psr0_config"].values():
        assert n["status"] == 200

    # Check config hash
    result = subprocess.check_output(client_args + ["kotekan_config_md5sum"], encoding="utf-8")
    assert "config_md5sum" in result
    assert "failed_checks" not in result

    print("TEST: Config hash matches after updating pulsar gating.")

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

    # Check config hash
    result = subprocess.check_output(client_args + ["kotekan_config_md5sum"], encoding="utf-8")
    assert "config_md5sum" in result
    assert "failed_checks" not in result

    print("TEST: Config hash matches after updating EW beam.")

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

    # Check config hash
    result = subprocess.check_output(client_args + ["kotekan_config_md5sum"], encoding="utf-8")
    assert "config_md5sum" in result
    assert "failed_checks" not in result
    print("TEST: Config hash matches after updating NS beam.")

    # Update beam offset
    result = subprocess.check_output(client_args + ["update-beam-offset", "10"], encoding="utf-8")
    result = json.loads(result)
    assert isinstance(result, dict)
    assert f"frb/update_beam_offset" in result
    for n in result[f"frb/update_beam_offset"].values():
        assert n["status"] == 200

    result = subprocess.check_output(client_args + ["kotekan-running-config"], encoding="utf-8")
    result = json.loads(result)
    assert isinstance(result, dict)
    assert f"config" in result

    # Check config hash
    result = subprocess.check_output(client_args + ["kotekan_config_md5sum"], encoding="utf-8")
    assert "config_md5sum" in result
    assert "failed_checks" not in result
    print("TEST: Config hash matches after updating beam offset.")

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
            "pulse_width": 1e-3,
            "rot_freq": 0.03e3,
            "phase_ref": [0.0],
            "t_ref": [58000.0],
            "segment": 0.0,
            "dm": 0.0,
            "coeff": [[0.0, 0.0]],
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

    # test status endpoint
    result = subprocess.check_output(client_args + ["status"], encoding="utf-8")
    result = json.loads(result)
    assert isinstance(result, dict)
    # check state
    assert "state" in result
    assert isinstance(result["state"], dict)
    # check blacklist
    assert "blacklist" in result
    assert list(result["blacklist"]["blacklist"].keys()) == ["http://coco/"]
    assert result["blacklist"]["blacklist"]["http://coco/"]["status"] == 200
    assert isinstance(result["blacklist"]["blacklist"]["http://coco/"]["reply"], list)
    # check node status and version
    for group in ["cluster", "receiver"]:
        assert f"status-{group}" in result
        for reply in result[f"status-{group}"]["status"].values():
            assert reply["status"] == 200
            assert reply["reply"]["running"]
        assert f"version-{group}" in result
        for reply in result[f"version-{group}"]["version"].values():
            assert reply["status"] == 200
    # check md5sums
    assert "config_md5sum" in result
    for reply in result["config_md5sum"].values():
        assert reply["status"] == 200

    # test baseband enpoint
    baseband_id = 0
    start_t = time.time()
    # trigger a baseband dump event
    event_data = {
        "event_id": baseband_id,
        "file_path": "/test/baseband_test",
        "start_unix_seconds": int(start_t),
        "start_unix_nano": int(1e9 * (start_t - int(start_t))),
        "duration_nano": 1000,
        "dm": 1.0,
        "dm_error": 0.1,
        "coco_report_type": "FULL",
    }
    result = requests.post(f"http://localhost:12055/baseband", json=event_data)
    assert result.status_code == 200
    result = result.json()
    assert "baseband" in result
    for reply in result["baseband"].values():
        assert reply["status"] == 200

    # check event present in status endpoint
    result = requests.get(
        f"http://localhost:12055/baseband-status", json={"coco_report_type": "FULL"}
    )
    assert result.status_code == 200
    result = result.json()
    assert "baseband" in result
    for reply in result["baseband"].values():
        assert reply["status"] == 200
        # Request never gets completed because there is no data flowing
        # assert str(baseband_id) in reply["reply"]

    # now check specifying the id
    # TODO: this will also not work yet for the same reason as above
    # result = requests.get(
    #     f"http://localhost:12055/baseband-status?event_id={baseband_id}",
    #     json={"coco_report_type": "FULL"},
    # )
    # assert result.status_code == 200
    # result = result.json()
    # print(result)
    # assert "baseband" in result
    # for reply in result["baseband"].values():
    #     assert reply["status"] == 200
    # assert reply["reply"]

    # TODO: check receiver config: bad inputs, gains
    # TODO check status: timestamp of frb-gain-dir

    # Check config hash
    result = subprocess.check_output(client_args + ["kotekan_config_md5sum"], encoding="utf-8")
    assert "config_md5sum" in result
    assert "failed_checks" not in result

    # Desync a node
    requests.post(f"http://localhost:12100/frb_gain", json={"frb_gain_dir": "/nothing/here"})

    # Check config hash (should fail now)
    result = subprocess.check_output(client_args + ["kotekan_config_md5sum"], encoding="utf-8")
    assert "config_md5sum" in result
    assert "failed_checks" in result

    # Wait for kotekan to start
    while True:
        result = subprocess.check_output(client_args + ["status-cluster"], encoding="utf-8")
        result = json.loads(result)
        assert isinstance(result, dict)
        assert "status" in result
        running = True
        for n in result["status"].values():
            if n["status"] != 200:
                running = False
                break
            if n["reply"] != {"running": True}:
                running = False
                break
        if running:
            break

    time.sleep(15)

    # Check config hash again after node restarted
    result = subprocess.check_output(client_args + ["kotekan_config_md5sum"], encoding="utf-8")
    assert "config_md5sum" in result
    assert "failed_checks" not in result

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
