"""For configuring coco from the config files.

Configuration file search order:

- `/etc/coco/coco.conf`
- `/etc/xdg/coco/coco.conf`
- `~/.config/coco/coco.conf`
- `COCO_CONFIG_FILE` environment variable

This is in order of increasing precendence, with options in later files
overriding those in earlier entries. Configuration is merged recursively by
`merge_dict_tree`.

Example config:

.. codeblock:: yaml

    # Configure the standard logging level
    log_level: "DEBUG"

    # Directory to load endpoint configuration from
    endpoint_dir: '../conf/endpoints'

    # Host and port to run the coco server
    host: localhost
    port: 12055

    # Port for prometheus metrics
    metrics_port: 12056

    # Number of workers that will process and forward requests
    n_workers: 2

    # Time before requests sent to nodes time out. Needs to be a string representing a timedelta in
    # the form `<int>h`, `<int>m`, `<int>s` or a combination of the three.
    timeout: 10s

    # Time before requests sent to coco time out.
    # This value should depend on how many layers your configuration files have. If a call to a
    # coco endpoint could take longer than this value, because it triggers many layered forward
    # calls you should increase this.
    # Needs to be a string representing a timedelta in
    # the form `<int>h`, `<int>m`, `<int>s` or a combination of the three.
    frontend_timeout: 10m

    # Groups of nodes that are managed by coco
    groups:
        gps_server:
            - carillon.chime:54321
        cluster:
            - localhost:12050
            - localhost:12000
        receiver_nodes:
            - recv1:12048
            - recv2:12048
        all:
            - localhost:12050
            - localhost:12000
            - recv1:12048
            - recv2:12048

    # Should we use (and where should we find) comet for tracking the coco config
    comet_broker:
        enabled: True
        host: recv1
        port: 12050

    # Initial cluster state
    load_state:
        cluster: "../conf/gpu.yaml"
        receiver: "../conf/recv.yaml"

    # Slack authorization token
    slack_token: "slack_bot_token"

    # Rules for dispatching logging messages to slack
    # These specify the logger path, the minimum level it applies to and the
    # slack channel the messages should go to.
    slack_rules:

        - logger: coco
          level: WARNING
          channel: coco-alerts

        - logger: coco.endpoint.update-pulsar-pointing-0
          level: INFO
          channel: pulsar-timing-ops

    # State paths to be excluded from reset.
    exclude_from_reset:
        - this/should/be/preserved
        - this_too
"""
import logging
import os
from pathlib import Path

import yaml


logger = logging.getLogger(__name__)

# TODO: pretty much all logging messages config out of this module are ignored
# as the default level has not yet been applied, some workaround should be
# figured out. For the moment, just uncomment the line below
# logging.getLogger().setLevel(logging.DEBUG)


class DefaultValue:
    """Tag a config node with a default value."""

    def __init__(self, value):
        self.value = value


class RequiredValue:
    """Tag a config node as being required."""

    pass


_config_skeleton = {
    "host": RequiredValue(),
    "port": DefaultValue(12055),
    "metrics_port": DefaultValue(9090),
    "log_level": DefaultValue("INFO"),
    "endpoint_dir": RequiredValue(),
    "n_workers": DefaultValue(1),
    "session_limit": DefaultValue(1000),
    "blocklist_path": DefaultValue("/var/lib/coco/blocklist.json"),
    "storage_path": DefaultValue("/var/lib/coco/state/"),
    "groups": RequiredValue(),
    "load_state": DefaultValue({}),
    "slack_token": DefaultValue(None),
    "slack_rules": DefaultValue([]),
    "queue_length": DefaultValue(0),
    "timeout": DefaultValue("10s"),
    "frontend_timeout": DefaultValue("10m"),
    "exclude_from_reset": DefaultValue([]),
}


def load_config(path=None):
    """Find and load the configuration from a file."""

    # Initialise with the default configuration
    config = _config_skeleton.copy()

    # Construct the configuration file path
    config_files = [
        "/etc/coco/coco.conf",
        "/etc/xdg/coco/coco.conf",
        "~/.config/coco/coco.conf",
    ]

    if "COCO_CONFIG_FILE" in os.environ:
        config_files.append(os.environ["COCO_CONFIG_FILE"])

    if path is not None:
        config_files.append(path)

    any_exist = False

    for cfile in config_files:

        # Expand the configuration file path
        absfile = Path(cfile).expanduser().resolve()

        if not absfile.exists():
            logger.debug(f"Could not find config file {absfile}")
            continue

        any_exist = True

        logger.info(f"Loading config file {cfile}")

        with absfile.open("r") as fh:
            conf = yaml.safe_load(fh)

        config = merge_dict_tree(config, conf)

    if not any_exist:
        raise RuntimeError("No configuration files available.")

    _validate_and_resolve(config)

    _load_endpoint_config(config)

    return config


def merge_dict_tree(a, b):
    """Merge two dictionaries recursively.

    The following rules applied:

      - Dictionaries at each level are merged, with `b` updating `a`.
      - Lists at the same level are combined, with that in `b` appended to `a`.
      - For all other cases, scalars, mixed types etc, `b` replaces `a`.

    Parameters
    ----------
    a, b : dict
        Two dictionaries to merge recursively. Where there are conflicts `b`
        takes preference over `a`.

    Returns
    -------
    c : dict
        Merged dictionary.
    """

    # Different types should return b
    if type(a) != type(b):
        return b

    # From this point on both have the same type, so we only need to check
    # either a or b.
    if isinstance(a, list):
        return a + b

    # Dict's should be merged recursively
    if isinstance(a, dict):
        keys_a = set(a.keys())
        keys_b = set(b.keys())

        c = {}

        # Add the keys only in a...
        for k in keys_a - keys_b:
            c[k] = a[k]

        # ... now the ones only in b
        for k in keys_b - keys_a:
            c[k] = b[k]

        # Recursively merge any common keys
        for k in keys_a & keys_b:
            c[k] = merge_dict_tree(a[k], b[k])

        return c

    # All other cases (scalars etc) we should favour b
    return b


def _validate_and_resolve(config):
    """Check that all required values are present and resolve default values."""

    stack = [("", config, "", None)]

    missing_values = []

    while stack:
        key, value, prefix, parent = stack.pop()

        # If node is a dict, add all child entries onto the stack for processing
        if isinstance(value, dict):
            for k, v in value.items():
                stack.append((k, v, f"{prefix}/{key}", value))

        # Replace default values
        if isinstance(value, DefaultValue):
            parent[key] = value.value

        if isinstance(value, RequiredValue):
            missing_values.append(f"{prefix}/{key}")

    if missing_values:
        for path in missing_values:
            logger.error(f'Resolved config missing required entry "{path}".')
        raise RuntimeError("Config missing required values.")


def _load_endpoint_config(config):
    """Load the endpoint config.

    The config is injected into the passed in config object.
    """

    config["endpoints"] = []

    endpoint_dir = Path(config["endpoint_dir"])

    def iterate_endpoint_dir(dir):
        for dir_entry in dir.iterdir():

            def load_endpoint(_file):
                # Only accept files ending in .conf as endpoint configs.
                # Endpoint config files starting with an underscore (_) are disabled.
                if _file.suffix == ".conf" and not _file.name.startswith("_"):
                    logger.debug(f"Loading endpoint config {_file}.")

                    # Remove .conf from the config file name to get the name of the endpoint
                    name = _file.stem

                    with _file.open("r") as fh:
                        try:
                            conf = yaml.safe_load(fh)
                        except yaml.YAMLError as exc:
                            logger.error(f"Failure reading YAML file {_file}: {exc}")

                    conf["name"] = name
                    # The last part of the relative path is '.'
                    conf["path"] = list(_file.relative_to(endpoint_dir).parents)[:-1]
                    logger.error(f"Loaded endpoint {name} with parents: {conf['path']}")

                    # TODO: validate the endpoint config in here
                    config["endpoints"].append(conf)

            if dir_entry.is_dir():
                iterate_endpoint_dir(dir_entry)
            else:
                load_endpoint(dir_entry)

    iterate_endpoint_dir(endpoint_dir)
