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

    # Port the redis server is listening on.
    redis_port: 6379

    # Number of workers that will process and forward requests
    n_workers: 2

    # Time before requests sent to nodes time out. Needs to be a string
    # representing a timedelta in the form `<int>h`, `<int>m`, `<int>s`
    # or a combination of the three.
    timeout: 10s

    # Time before requests sent to coco time out.
    #
    # This value should depend on how many layers your configuration files have.
    # If a call to a coco endpoint could take longer than this value, because
    # it triggers many layered forward calls you should increase this.
    #
    # Needs to be a string representing a timedelta in the form `<int>h`,
    # `<int>m`, `<int>s` or a combination of the three.
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

import click
import yaml

from .util import yaml_load

logger = logging.getLogger(__name__)

# TODO: pretty much all logging messages config out of this module are ignored
# as the default level has not yet been applied, some workaround should be
# figured out. For the moment, just uncomment the line below
# logging.getLogger().setLevel(logging.DEBUG)


# The default coco daemon port
DEFAULT_PORT = 12055

# This is a sentinel to catch required values which haven't been set
RequiredValue = object()

_config_skeleton = {
    "host": RequiredValue,
    "port": DEFAULT_PORT,
    "metrics_port": 9090,
    "redis_port": 6379,
    "log_level": "INFO",
    "endpoint_dir": RequiredValue,
    "n_workers": 1,
    "session_limit": 1000,
    "blocklist_path": "/var/lib/coco/blocklist.json",
    "storage_path": "/var/lib/coco/state/",
    "groups": RequiredValue,
    "load_state": {},
    "slack_token": None,
    "slack_rules": [],
    "queue_length": 0,
    "timeout": "10s",
    "frontend_timeout": "10m",
    "exclude_from_reset": [],
    "debug_connections": False,
    "comet_broker": {"enabled": True},
}


def load_config(
    path: str | os.PathLike | None = None, cli: bool = False, testing: bool = False
) -> None:
    """Find and load the configuration from a file.

    Parameters
    ----------
    path : path-like, optional
        An optional config file path given on the command line.  If such a path
        is given, it _must_ exist.
    cli : bool, optional
        True if we're loading a local config for the client.  This affects the
        default config used.  Default is False
    testing : bool, optional
        True if cocod was invoked with --testing.  This skips loading config from
        the default paths.  Default is False.
    """
    # Initialise with the default configuration.  For the client, this is
    # only a host and a port.
    if cli:
        config = {"host": RequiredValue, "port": DEFAULT_PORT}
    else:
        config = _config_skeleton.copy()

    # Construct the configuration file path.  The --testing flag forces us
    # to skip all of the default paths, even if they exist.
    if testing:
        config_files = []
    else:
        config_files = [
            "/etc/coco/coco.conf",
            "/etc/xdg/coco/coco.conf",
            "~/.config/coco/coco.conf",
        ]

    if "COCO_CONFIG_FILE" in os.environ:
        envpath = os.environ["COCO_CONFIG_FILE"]
        config_files.append(envpath)
    else:
        envpath = None

    if path is not None:
        config_files.append(path)

    any_exist = False

    for cfile in config_files:
        # Expand the configuration file path
        absfile = Path(cfile).expanduser().resolve()

        if not absfile.exists():
            # Explicitly-specified paths must exist
            if path and cfile == path:
                raise click.ClickException(
                    f"Config file specified on command line not found: {absfile}"
                )
            if envpath and cfile == envpath:
                raise click.ClickException(
                    f"Config file specified via COCO_CONFIG_FILE not found: {absfile}"
                )
            logger.debug(f"Config file {absfile} not present.")
            continue

        any_exist = True

        logger.info(f"Loading config file {cfile}")

        try:
            with absfile.open("r", encoding="utf-8") as fh:
                conf = yaml_load(fh)
        except (OSError, ValueError, UnicodeDecodeError, yaml.YAMLError) as e:
            raise click.ClickException(f"Error reading {absfile}: {e}") from e

        config = merge_dict_tree(config, conf)

    if not any_exist:
        raise click.ClickException("No configuration files available.")

    # Validate config
    _validate_and_resolve(config)

    # Local endpoints are not loaded in the CLI
    if not cli:
        # Load the endpoints
        endpoint_tree = load_endpoint_tree(Path(config["endpoint_dir"]))

        # We only record the endpoint list per se, not the whole top-level group
        config["endpoints"] = endpoint_tree["endpoints"]

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
    if type(a) is not type(b):
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


def _validate_and_resolve(config: dict) -> None:
    """Check that all required values are present and resolve default values."""

    missing_values = []

    for key, value in config.items():
        if value is RequiredValue:
            missing_values.append(key)

    if missing_values:
        raise click.ClickException(
            "Missing required config:\n  " + "\n  ".join(missing_values)
        )


def load_endpoint(path: Path) -> dict | None:
    """Read an endpoint from `path`.

    Returns the parsed endpoint config entry, or None if `path` wasn't an
    endpoint file
    """
    # A file called "__meta.conf" (two underscores) can be used to set metadata
    # about the containing endpoint group.
    meta = path.name == "__meta.conf"

    # Only accept files ending in .conf as endpoint configs.
    # Endpoint config files starting with an underscore (_) are disabled (except
    # a __meta.conf file).
    if not meta and (path.suffix != ".conf" or path.name.startswith("_")):
        # Not a valid endpoint file
        logger.debug(f"Ignoring invalid/disabled endpoint {path}.")
        return None

    logger.debug(f"Loading endpoint config {path}.")

    try:
        with path.open("r", encoding="utf-8") as fh:
            conf = yaml_load(fh)
    except (OSError, ValueError, UnicodeDecodeError, yaml.YAMLError) as e:
        raise click.ClickException(f"Failure reading endpoint {path}: {e}") from e

    # Extra endpoint metadata
    conf["meta"] = meta
    conf["tree"] = False

    # A "name" field in an endpoint file is not allowed
    if "name" in conf:
        raise click.ClickException(f"spurious 'name' found in endpoint {path}")

    # Remove .conf from the config file name to get the name of the endpoint
    conf["name"] = path.stem

    return conf


def load_endpoint_tree(path):
    """Iterate over a directory `path` in the endpoint tree.

    Returns an endpoint tree config for the directory,
    containing the endpoints and subtrees found within.
    """
    tree = {
        "name": path.name,
        "tree": True,
        "description": "Unremarkable endpoint tree",
        "endpoints": [],
    }
    for dir_entry in path.iterdir():
        if dir_entry.is_dir():
            # Parse the subtree
            subtree = load_endpoint_tree(dir_entry)

            # The subtree is only added if it's not empty
            if subtree["endpoints"]:
                tree["endpoints"].append(subtree)
        else:
            endpoint = load_endpoint(dir_entry)

            # Skip if nothing was loaded
            if not endpoint:
                continue

            if endpoint["meta"]:
                # If this was a __meta.conf file, merge (select) data into the
                # tree config
                for key in {"description", "summary"}:
                    if key in endpoint:
                        tree[key] = endpoint[key]
            else:
                # otherwise, delete the "meta" key and append endpoint
                # to the tree's list
                del endpoint["meta"]
                tree["endpoints"].append(endpoint)

    return tree
