"""coco state module."""
import collections
import hashlib
import logging
import os
from typing import List, Dict
import msgpack as msgpack
import yaml

from .util import PersistentState
from .exceptions import InternalError

logger = logging.getLogger(__name__)


def my_construct_mapping(self, node, deep=False):
    """Make yaml loader always convert integer keys to strings."""
    data = self.construct_mapping_org(node, deep)
    return {(str(key) if isinstance(key, int) else key): data[key] for key in data}


yaml.SafeLoader.construct_mapping_org = yaml.SafeLoader.construct_mapping
yaml.SafeLoader.construct_mapping = my_construct_mapping


class State:
    """Representation of the complete state of all hosts (configs) coco controls."""

    def __init__(
        self,
        log_level,
        storage_path: os.PathLike,
        default_state_files: Dict[str, str],
        exclude_from_reset: List[str],
    ):
        """
        Construct the state.

        Parameters
        ----------
        log_level : str
            Log level to use inside this class.
        storage_path : os.PathLike
            Path to the persistent state storage.
        default_state_files : Dict[str, str]
            Yaml files that are loaded to build the default state. Keys are state paths.
        exclude_from_reset : List[str]
            State paths that should be preserved during reset.
        """
        self.default_state_files = default_state_files
        self.exclude_from_reset = exclude_from_reset

        # Initialise persistent storage
        self._storage = PersistentState(storage_path)

        # Update state with content from persistent state loaded from disk
        if not self._storage.state:
            with self._storage.update():
                self._storage.state = dict()

        # If the state storage was empty load state from yaml config files
        if self.is_empty():
            self._load_default_state()

        logger.setLevel(log_level)

    def write(self, path, value, name=None):
        """
        Write (or overwrite) a value in the state.

        Parameters
        ----------
        path : str
            `"path/to/write/value/to"`. If `name` is `None`, the last part of the path will be the
            name of the entry.
        value
            The value.
        name : str
            The name of the entry. If this is `None` the last part of `path` will be used.
        """
        # Update persistent state
        with self._storage.update():
            if name is None:
                element, name = self._find_new(path)
            else:
                element = self._find(path)

            element[name] = value

    def read(self, path, name=None):
        """
        Read a value from the state.

        Parameters
        ----------
        path : str
            `"path/to/the/value"`. If `name` is `None`, the last part of this is the name of the
            value to read.
        name : str
            Name of the value. If this is `None`, the last part of `path` will be used.

        Returns
        -------
        The value.
        """
        element = self._find(path)
        if name:
            return element[name]
        return element

    def extract(self, path: str) -> dict:
        """
        Extract a part of the state containing the whole given path.

        Parameters
        ----------
        path : str
            `"path/to/the/value"`. The last part of this is the name of the value to read.

        Returns
        -------
        dict
            A dict that contains the root level of the state and the whole requested path, but only
            the values in the requested entry.
        """
        value = self.read(path)

        # parse the path: split it at slashes and throw away empty parts
        parts = path.split("/")
        parts = list(filter(lambda part: part != "", parts))

        def pack(p: List[str], v) -> dict:
            """
            Pack a value into a nested dict.

            Parameters
            ----------
            p : list
                Path for nested dict.
            v
                Value.

            Returns
            -------
            dict
                A nested dict containing the full given path and only the one given value at the
                bottom.
            """
            if len(p) == 0:
                return v
            if len(p) == 1:
                return dict({p[0]: value})
            return dict({p[0]: pack(p[1:], v)})

        return pack(parts, value)

    def read_from_file(self, path, file):
        """
        Write into the state from what is read from a file.

        Parameters
        ----------
        path : str
            `"path/to/the/new/state/entry"`
        file : str
            Name of the file to read from.
        """
        logger.debug(f"Loading state {path} from file {file}.")

        # Update persistent state
        with self._storage.update():
            element, name = self._find_new(path)

            with open(file, "r") as stream:
                try:
                    element[name] = yaml.safe_load(stream)
                except yaml.YAMLError as exc:
                    logger.error(f"Failure reading YAML file {file}: {exc}")

    def _find(self, path):
        """
        Find `"an/entry/by/path"` and return the entry.

        Parameters
        ----------
        path : str
            `"path/to/the/entry"`

        Returns
        -------
            The state entry.
        """
        if path is None or path == "" or path == "/":
            return self._storage.state
        paths = path.split("/")
        element = self._storage.state
        for i in range(0, len(paths)):
            if paths[i] == "":
                continue
            try:
                element = element[paths[i]]
            except KeyError:
                raise InternalError("Path not found in state: {}".format(path))
        return element

    def _find_new(self, path):
        """
        Find `"an/entry/by/path/and/name"` and return the parent entry and `name` of the new entry.

        Parameters
        ----------
        path : str
            `"path/to/the/entry"`

        Returns
        -------
            The parent entry and the name of the new entry (can be used like
            `parent_entry[name] = <new_value>`).
        """
        if path is None or path == "" or path == "/":
            raise RuntimeError("Can't create new state entry at root level.")
        paths = path.split("/")
        element = self._storage.state
        for i in range(0, len(paths) - 1):
            try:
                element = element[paths[i]]
            except KeyError:
                element[paths[i]] = dict()
                element = element[paths[i]]
        return element, paths[-1]

    def find_or_create(self, path):
        """
        Find or create `"a/path/in/the/state"`.

        Parameters
        ----------
        path : str
            `"a/path/in/the/state"`.

        Returns
        -------
        dict
            The part of the state the path points at.
        """
        if path is None:
            return None
        if path is None or path == "" or path == "/":
            return self._storage.state
        paths = path.split("/")

        # Update persistent state
        with self._storage.update():
            element = self._storage.state
            for i in range(0, len(paths)):
                try:
                    element = element[paths[i]]
                except TypeError:
                    raise RuntimeError(
                        f"coco.state: part {i} of path {path} is of type "
                        f"{type(element).__name__}. Can't overwrite it with a sub-"
                        f"state block."
                    )
                except KeyError:
                    element[paths[i]] = dict()
                    element = element[paths[i]]
        return element

    def hash(self, path=None):
        """
        Calculate the hash of any part of the state. or of the whole state if `path` is `None`.

        Parameters
        ----------
        path : str
            `"path/to/entry"`. Default `None`.

        Returns
        -------
            The hash for the selected part of the state.
        """
        element = self._find(path)
        return self.hash_dict(element)

    @staticmethod
    def hash_dict(dict_: Dict):
        """
        Get a hash of the given dict.

        Parameters
        ----------
        dict_ : dict
            The dict to hash.

        Returns
        -------
        Hash
        """
        serialized = msgpack.packb(State.sort_dict(dict_), use_bin_type=True)
        _md5 = hashlib.md5()
        _md5.update(serialized)
        return _md5.hexdigest()

    @staticmethod
    def sort_dict(dict_: Dict):
        """
        Recursively sort a dictionary.

        Parameters
        ----------
        dict_ : dict
            The dictionary to sort.

        Returns
        -------
        collections.OrderedDict
            The ordered dictionary.
        """
        ordered = collections.OrderedDict(sorted(dict_.items(), key=lambda t: t[0]))
        for key in ordered.keys():
            if isinstance(ordered[key], dict):
                ordered[key] = State.sort_dict(ordered[key])
            if isinstance(ordered[key], list):
                ordered[key] = State.sort_list(ordered[key])
        return ordered

    @staticmethod
    def sort_list(list_: Dict):
        """
        Recursively sort all dictionaries in a list.

        Parameters
        ----------
        list_ : list
            The list to search for dicts to be sorted.

        Returns
        -------
        list
            The same list, but all dictionaries found in this list and in any dicts and
            lists it contains at any depths are sorted. Note that the list and any
            contained lists are not sorted themselves.
        """
        for i, item in enumerate(list_):
            if isinstance(item, dict):
                list_[i] = State.sort_dict(item)
            if isinstance(item, list):
                list_[i] = State.sort_list(item)
        return list_

    def is_empty(self):
        """
        Tell if the state is empty.

        Returns
        -------
        bool
            True if the state is empty, False otherwise.
        """
        return len(self._storage.state) == 0

    def _load_default_state(self):
        """Load internal state from yaml files."""
        for path, file in self.default_state_files.items():
            self.read_from_file(path, file)

    async def process_post(self, request: dict):
        """
        Process the POST request to reset the state.

        Clear the internal state and re-load YAML files to restore default state.
        """
        # back up excluded paths
        excluded = dict()
        for path in self.exclude_from_reset:
            split_path = path.split("/")
            element = self._storage.state
            for i in range(0, len(split_path)):
                try:
                    element = element[split_path[i]]
                except KeyError as key:
                    logger.debug(
                        "Can't exclude {} from config. Path not found in state.".format(
                            path
                        )
                    )
                    break
            excluded[path] = element

        # Reset persistent state
        with self._storage.update():
            self._storage.state = dict()
        self._load_default_state()

        # recover excluded paths
        for path, content in excluded.items():
            with self._storage.update():
                location, new_entry = self._find_new(path)
                location[new_entry] = content
