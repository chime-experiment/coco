"""coco: A Config Controller."""
from ._version import get_versions

__version__ = get_versions()["version"]
del get_versions

from .endpoint import Endpoint
from .slack import SlackExporter
from .master import Master
