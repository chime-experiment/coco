"""coco: A Config Controller."""

import logging
from importlib.metadata import PackageNotFoundError, version

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
