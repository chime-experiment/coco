"""Conditions for scheduling and calling endpoints."""

from typing import Dict
import logging
from pydoc import locate

from . import State
from .exceptions import ConfigError

logger = logging.getLogger(__name__)


class Condition:
    """Condition on state."""

    def __init__(self, name, conf: Dict):
        """
        Constructor.

        Parameters
        ----------
        name : str
            Name of the endpoint this condition is for.
        conf : dict
            Condition configuration (see docs).
        """
        self.name = name
        try:
            path = conf["path"]
            val_type = conf["type"]
        except KeyError:
            ConfigError(
                f"Endpoint '{self.name}' conditions must include fields 'path' and 'type'."
            )
        val_type = locate(val_type)
        if val_type is None:
            ConfigError(f"'require_state' of endpoint {self.name} is of unknown type.")
        self.checks = {"path": path, "type": val_type}
        val = conf.get("value", None)
        if val is not None:
            self.checks["value"] = val_type(val)

    def check(self, state: State):
        """
        Check for the condition against the given state.

        Parameters
        ----------
        state : :class:`State`
            The state to check the condition against.

        Returns
        -------
        True if the condition is satisfied, False otherwise.
        """
        # Look for value in state
        try:
            state_val = state.read(self.checks["path"])
        except KeyError:
            logger.info(
                f"Condition for /{self.name} not met: {self.checks['path']} doesn't exist."
            )
            return False
        # Check type in state
        if not isinstance(state_val, self.checks["type"]):
            logger.info(
                f"Condition for /{self.name} not met: "
                f"{self.checks['path']} type is not {self.checks['type']}."
            )
            return False
        # Check value if required
        val = self.checks.get("value", None)
        if val is not None:
            if state_val != val:
                logger.info(
                    f"Condition for /{self.name} not met: "
                    f"{self.checks['path']} != {self.checks['value']}."
                )
                return False
        return True
