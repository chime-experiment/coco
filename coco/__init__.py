"""coco: A Config Controller."""
from ._version import get_versions

__version__ = get_versions()["version"]
del get_versions

from .slack import SlackExporter
from .task_pool import TaskPool
from .request_forwarder import RequestForwarder
from .endpoint import Endpoint
from .master import Master
