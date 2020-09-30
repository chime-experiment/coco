Configuration
================================

coco's main configuration file has the following options. It can be passed to coco with `coco[d] -c path/to/coco.conf`.

log_level : `str`
    The global log level. Can be one of `CRITICAL`, `ERROR`, `WARNING`, `INFO` or `DEBUG`. Default `INFO`.
host: `str`
    Host the coco server (`cocod`) is run on.
port: `int`
    Port the coco server (`cocod`) should be run on. Default `12055`.
metrics_port: `int`
    Port cocod should run its metrics server on. Default `9090`.
endpoint_dir: `str`
    Path where endpoint config files are located.
n_workers: `int`
    Number of sanic workers to start for the frontend of `cocod`. Default `1`.
session_limit: `int`
    Maximum number of tasks being executed concurrently by request forwarder. A higher number will use more memory. Default `1000`.
blocklist_path: `str`
    Path to persistent blocklist storage file. Default `/var/lib/coco/blocklist.json`.
storage_path: `str`
    Path to persistent state storage. Default `/var/lib/coco/state/`.
groups:
    Groups of nodes that are managed by coco. Contains key-value pairs where the key is
    the name of the group (`str`) and the value is a list of `str` in the format
    `host:port`.

    Example:

.. code-block:: yaml

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

load_state:
    Initial cluster state.
    Contains key-value pairs that are state paths and file system paths. The files
    located at the latter locations are loaded into the prior parts of the state when
    resetting the state. Default: `None`.

    Example:

.. code-block:: yaml

    load_state:
        cluster: "../conf/gpu.yaml"
        receiver: "../conf/recv.yaml"

slack_token: `str`
    Slack authorization token. Default: `None`.
slack_rules: list
    Rules for dispatching logging messages to slack.
    These specify the logger path, the minimum level it applies to and the
    slack channel the messages should go to. Default: `None`.

    Example:

.. code-block:: yaml

    slack_rules:

        - logger: coco
          level: WARNING
          channel: coco-alerts

        - logger: coco.endpoint.update-tracking-pointing-0
          level: INFO
          channel: pulsar-timing-ops

queue_length: int
    Length of the endpoint request queue between front- end backend, managed by redis.
    Default `0`.
timeout: str
    Time before requests sent to nodes time out.
    A string representing a timedelta in the form `<int>h`, `<int>m`,
    `<int>s` or a combination of the three. Default `10s`.
frontend_timeout: str
    Time before requests sent to coco time out.
    This value should depend on how many layers your configuration files have. If a call
    to a coco endpoint could take longer than this value, because it triggers many
    layered forward calls you should increase this.
    A string representing a timedelta in the form `<int>h`, `<int>m`,
    `<int>s` or a combination of the three. Default `10m`.
exclude_from_reset: list
    A list of strings that are state paths to be excluded from state resets. Default:
    `None`
