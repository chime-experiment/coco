"""coco: A Config Controller."""

import logging
from importlib.metadata import PackageNotFoundError, version

from .check import (
    Check,
    IdenticalReplyCheck,
    ReplyCheck,
    StateHashReplyCheck,
    StateReplyCheck,
    TypeReplyCheck,
    ValueReplyCheck,
)
from .core import Core
from .endpoint import Endpoint, LocalEndpoint
from .request_forwarder import CocoForward, ExternalForward, RequestForwarder
from .result import Result
from .state import State
from .task_pool import TaskPool

__all__ = [
    "TaskPool",
    "Result",
    "Check",
    "ReplyCheck",
    "IdenticalReplyCheck",
    "TypeReplyCheck",
    "ValueReplyCheck",
    "StateHashReplyCheck",
    "StateReplyCheck",
    "RequestForwarder",
    "ExternalForward",
    "CocoForward",
    "State",
    "Endpoint",
    "LocalEndpoint",
    "Core",
]

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s [%(process)d] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="[%Y-%m-%d %H:%M:%S %z]",
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Get version
try:
    __version__ = version("coco")
except PackageNotFoundError:
    # Package not installed
    __version__ = "0.0.0"
del version
