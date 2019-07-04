"""Run coco script for unit tests."""

import subprocess
import os
import tempfile
import time
import json

COCO = os.path.dirname(os.path.abspath(__file__)) + "/../../scripts/coco"
CONFIG = {
    "comet_broker": {"enabled": False},
    "metrics_port": 12056,
    "host": "localhost",
    "port": 12055,
    "log_level": "DEBUG",
}
CLIENT_ARGS = [
    os.path.dirname(os.path.abspath(__file__)) + "/../../scripts/coco-client",
    "-s",
    "json",
    "-r",
    "FULL",
]


class Runner:
    """Coco Runner for unit tests."""

    def __init__(self, config, endpoints):
        self.coco, self.configfile, self.endpointdir = self.start_coco(config, endpoints)
        time.sleep(1)

    def __del__(self):
        """Destructor."""
        self.stop_coco()

    def client(self, command, data=None):
        """Make coco-client script call a coco endpoint."""
        if data:
            data = list(data.values())
            for i in range(len(data)):
                data[i] = str(data[i])
        else:
            data = []
        result = subprocess.check_output(
            CLIENT_ARGS + ["-c", self.configfile.name, command] + data, encoding="utf-8"
        )
        print(result)
        result = json.loads(result)
        return result

    @staticmethod
    def start_coco(config, endpoint_configs):
        """Start coco with a given config."""
        CONFIG.update(config)

        # Write endpoint configs to file
        endpointdir = tempfile.TemporaryDirectory()
        CONFIG["endpoint_dir"] = endpointdir.name
        for name, endpoint_conf in endpoint_configs.items():
            with open(os.path.join(endpointdir.name, name + ".conf"), "w") as outfile:
                json.dump(endpoint_conf, outfile)

        # Write config to file
        configfile = tempfile.NamedTemporaryFile("w")
        json.dump(CONFIG, configfile)
        configfile.flush()

        coco = subprocess.Popen([COCO, "-c", configfile.name])
        return coco, configfile, endpointdir

    def stop_coco(self):
        """Stop coco script."""
        self.coco.terminate()
        self.coco.communicate()
