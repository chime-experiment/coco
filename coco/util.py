"""
Utility functions.

The str2time* functions were stolen from dias
(https://github.com/chime-experiment/dias/blob/master/dias/utils/string_converter.py).
"""
import re
from datetime import timedelta
import os
import copy
import json
from urllib.parse import urlparse

from atomicwrites import atomic_write


TIMEDELTA_REGEX = re.compile(r"((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?")


def str2timedelta(time_str):
    """
    Convert a string to a timedelta.

    Parameters
    ----------
    time_str : str
        A string representing a timedelta in the form `<int>h`, `<int>m`,
        `<int>s` or a combination of the three.

    Returns
    -------
    :class:`datetime.timedelta`
        The converted timedelta.
    """
    # Check for simple numeric seconds
    try:
        seconds = int(time_str)
        return timedelta(seconds=seconds)
    except ValueError:
        pass

    # Otherwise parse time
    parts = TIMEDELTA_REGEX.match(time_str)
    if not parts:
        return
    parts = parts.groupdict()
    time_params = {}
    for (name, param) in parts.items():
        if param:
            time_params[name] = int(param)
    return timedelta(**time_params)


def str2total_seconds(time_str):
    """
    Convert that describes a timedelta directly to seconds.

    Parameters
    ----------
    time_str : str
        A string representing a timedelta in the form `<int>h`, `<int>m`,
        `<int>s` or a combination of the three.

    Returns
    -------
    float
        Timedelta in seconds.
    """
    return str2timedelta(time_str).total_seconds()


class Host:
    """Represents a host URL.

    Parameters
    ----------
    host_url
        The URL for the host in form `<hostname>:<port>`.
    """

    def __init__(self, host_url: str):
        self._url = urlparse(self.format_host(host_url))
        self.hostname = self._url.hostname
        self.port = self._url.port

    def join_endpoint(self, endpoint: str):
        """Get a URL for the given endpoint."""
        return self._url._replace(path=endpoint).geturl()

    def url(self):
        """Return string representation of the http://host:port/."""
        return self._url.geturl()

    def __eq__(self, other):
        return (self.hostname == other.hostname) and (self.port == other.port)

    def __hash__(self):
        return hash((self.hostname, self.port))

    def __str__(self):
        return f"{self.hostname}:{self.port}"

    def __format__(self, format_spec):
        if self.port is None:
            return self.hostname
        else:
            return f"{self.hostname}:{self.port}"

    @staticmethod
    def format_host(host: str) -> str:
        """Transform a <host>:<port> string into a proper HTTP URI.

        Parameters
        ----------
        host
            <host>:<port> string.

        Returns
        -------
        uri
            Full URI string.
        """
        if not host.startswith("http://"):
            host = "http://" + host
        if not host.endswith("/"):
            host = host + "/"
        return host

    @staticmethod
    def print_list(hosts) -> str:
        """Print a list of hosts."""
        return "[" + (", ".join([f"{host}" for host in hosts])) + "]"


class PersistentState:
    """Persist JSON like state on disk.

    Parameters
    ----------
    path
        Path to file to serialise the state in.
    """

    def __init__(self, path: os.PathLike):
        self._path = path
        self._update = False

        if path.exists():
            with path.open("r") as fh:
                self._state = json.load(fh)
        else:
            self._state = None

    @property
    def state(self):
        """Get the state."""

        if self._update:
            return self._tmp_state
        else:
            return copy.deepcopy(self._state)

    @state.setter
    def state(self, value):
        """Set the state if in update mode."""

        if self._update:
            self._tmp_state = value
        else:
            raise RuntimeError("Cannot update state outside of a `.update() context.")

    def commit(self):
        """Commit the modified state."""

        if not self._update:
            raise RuntimeError("Must be in update mode to call commit.")

        # Take a reference to the old state in case of failure and we need to revert
        old_state = self._state

        # Lock to ensure the state can only be read for states that were
        # successfully committed
        try:
            # Try to update and write out the state
            self._state = copy.deepcopy(self._tmp_state)
            with atomic_write(self._path, overwrite=True) as f:
                json.dump(self._state, f)

        except Exception as e:
            # If anything happens, rollback to the old state
            self._state = old_state
            raise RuntimeError("Could not commit state.") from e

    def update(self):
        """Return a Context Manager that can atomically update the state.

        Returns
        -------
        updater : context manager
        """
        return PersistentState._WriterManager(self)

    class _WriterManager:
        """Context manager for modifying a PersistentState.

        Attributes
        ----------
        state : json serialisable
            Modify this attribute to the desired state. This will be serialised
            into the state file.
        """

        def __init__(self, ps):
            self._ps = ps

        def __enter__(self):
            self._ps._tmp_state = self._ps.state
            self._ps._update = True
            return None

        def __exit__(self, *args):
            try:
                self._ps.commit()
            finally:
                # Regardless of what happens we should leave update mode
                self._ps._update = False
