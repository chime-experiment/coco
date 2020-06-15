"""coco: A Config Controller."""
import logging
from ._version import get_versions

__version__ = get_versions()["version"]
del get_versions

from .task_pool import TaskPool
from .result import Result
from .check import (
    Check,
    ReplyCheck,
    IdenticalReplyCheck,
    TypeReplyCheck,
    ValueReplyCheck,
    StateHashReplyCheck,
    StateReplyCheck,
)
from .request_forwarder import RequestForwarder, ExternalForward, CocoForward
from .state import State
from .endpoint import Endpoint, LocalEndpoint
from .core import Core

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s [%(process)d] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="[%Y-%m-%d %H:%M:%S %z]",
)
handler.setFormatter(formatter)
logger.addHandler(handler)
