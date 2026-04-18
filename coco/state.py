"""coco state module."""

import logging
import os
from pathlib import Path

import jinja2

from .exceptions import InternalError, InvalidUsage
from .result import Result
from .util import Host, PersistentState, hash_dict, yaml_load

logger = logging.getLogger(__name__)

# This is the name of the file (in the "storage_path") containing the active state.
ACTIVE = "active"


class State:
    """This is the complete state of all hosts (configs) coco controls.

    Parameters
    ----------
    storage_path : os.PathLike
        Path to the persistent state storage.
    default_state_files : dict[str, str]
        Yaml files that are loaded to build the default state. Keys are state paths.
    exclude_from_reset : list[str]
        State paths that should be preserved during reset.
    """

    def __init__(
        self,
        storage_path: os.PathLike,
        default_state_files: dict[str, str],
        exclude_from_reset: list[str],
    ) -> None:
        self.default_state_files = default_state_files
        self.exclude_from_reset = exclude_from_reset
        self._storage_path = storage_path

        # List saved states on disk
        self._saved_states = set()
        for item in Path(self._storage_path).iterdir():
            if item.is_file() and item.name != ACTIVE:
                self._saved_states.add(item.name)
        if self._saved_states:
            logger.info(
                f"Found {len(self._saved_states)} previously saved states on disk: "
                + self._saved_states_list
            )
        else:
            logger.info("No saved states found.")

        # Initialise persistent storage with content loaded from disk, which
        # may not exist
        self._storage = PersistentState(Path(storage_path, ACTIVE), missing_ok=True)

        # If the state storage was empty load state from yaml config files
        if self.is_empty():
            logger.info("Internal state empty. Loading default state...")
            self._load_default_state()

    def write(self, path, value, name=None):
        """
        Write (or overwrite) a value in the state.

        Parameters
        ----------
        path : str
            `"path/to/write/value/to"`. If `name` is `None`, the last part of
            the path will be the name of the entry.
        value
            The value.
        name : str
            The name of the entry. If this is `None` the last part of `path`
            will be used.
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
            `"path/to/the/value"`. If `name` is `None`, the last part of this
            is the name of the value to read.
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
            `"path/to/the/value"`. The last part of this is the name of the value to
            read.

        Returns
        -------
        dict
            A dict that contains the root level of the state and the whole
            requested path, but only the values in the requested entry.
        """
        value = self.read(path)

        # parse the path: split it at slashes and throw away empty parts
        parts = path.split("/")
        parts = list(filter(lambda part: part != "", parts))

        def pack(p: list[str], v) -> dict:
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
                A nested dict containing the full given path and only the one
                given value at the bottom.
            """
            if len(p) == 0:
                return v
            if len(p) == 1:
                return {p[0]: value}
            return {p[0]: pack(p[1:], v)}

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
        logger.debug(f"Loading file {file} into state path '{path}'.")

        # Update persistent state
        with self._storage.update():
            if len(path) != 0:
                element, name = self._find_new(path)

            new_state = load_kotekan_config_file(file)

            # Don't load state parts that are excluded from reset
            self._exclude_paths(path, new_state)

            if len(path) == 0:
                self._storage.state = new_state
            else:
                element[name] = new_state

    def _exclude_paths(self, path, state):
        """
        Remove excluded paths from a state (in-place).

        If the excluded paths are set to `foo/bar` and `path` is `foo`, a this
        function would take a `state = {'bar': 0}` and make it a `state = {}`.

        Parameters
        ----------
        path : str
            Prefix to 'state' when looking for parts to exclude.
        state : dict
            The state to remove excluded parts from.
        """
        if not isinstance(state, dict):
            return
        for excluded in self.exclude_from_reset:
            if excluded.startswith(path):
                if len(path) != 0:
                    # remove the `/` as well
                    excluded = excluded[len(path) + 1 :]
                path_first = excluded.split("/")[0]
                if path_first in state:
                    self._exclude_paths(path_first, state[path_first])
                if excluded in state:
                    del state[excluded]

    def exists(self, path):
        """
        Check if a path exists in the state.

        Parameters
        ----------
        path : str
            A path like "path/to/state/entry" or "/path/to/state/entry".

        Returns
        -------
        bool
            True, if the path exists in the state.
        """
        try:
            self._find(path)
        except InternalError:
            return False
        return True

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

        Raises
        ------
        InternalError
            If the path doesn't exist.
        """
        if path is None or path == "" or path == "/":
            return self._storage.state
        paths = path.split("/")
        element = self._storage.state
        for p in paths:
            if p == "":
                continue
            try:
                element = element[p]
            except KeyError as e:
                raise InternalError(f"Path not found in state: {path}") from e
        return element

    def _find_new(self, path):
        """
        Find `"an/entry/by/path/and/name"` and return the parent entry and
        `name` of the new entry.

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
                element[paths[i]] = {}
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
            for i, p in enumerate(paths):
                try:
                    element = element[p]
                except TypeError as e:
                    raise RuntimeError(
                        f"coco.state: part {i} of path {path} is of type "
                        f"{type(element).__name__}. Can't overwrite it with a sub-"
                        f"state block."
                    ) from e
                except KeyError:
                    element[p] = {}
                    element = element[p]
        return element

    def hash(self, path=None):
        """
        Calculate the hash of any part of the state. or of the whole state if
        `path` is `None`.

        Parameters
        ----------
        path : str
            `"path/to/entry"`. Default `None`.

        Returns
        -------
            The hash for the selected part of the state.
        """
        element = self._find(path)
        return hash_dict(element)

    @property
    def _saved_states_list(self) -> str:
        """Print a list of saved states."""
        if not self._saved_states:
            return ""

        return " ".join(sorted(self._saved_states))

    def is_empty(self):
        """Tell if the state is empty.

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

    async def reset_state(self, _: dict | None = None):
        """
        Process the POST request to reset the state.

        Clear the internal state and re-load YAML files to restore default state.
        """
        excluded = self._backup_excluded_paths()

        # Reset persistent state
        with self._storage.update():
            self._storage.state = {}
        self._load_default_state()

        self._recover_excluded_paths(excluded)

    async def save_state(self, request: dict = {}):
        """Process the POST request to save (backup) the state.

        The request dictionary should contain an item with key "name" that
        holds a string with the name of the saved state.
        """
        # get request parameters
        name = request.get("name", "backup")
        if name == ACTIVE:
            raise InvalidUsage(
                f"Can't use {ACTIVE} for saved state. "
                "This name is reserved. Choose something else."
            )

        # Don't allow writing out of the storage_path
        if name != Path(name).name:
            raise InvalidUsage(
                f"Cannot use '{name}' as a state.  Choose something else."
            )

        # only overwrite an existing state if requested explicitly
        if name in self._saved_states:
            overwrite = bool(request.get("overwrite", False))
            if not overwrite:
                raise InvalidUsage(
                    f"Saved state '{name}' already exists. Choose something "
                    "else or try again with 'overwrite=True'."
                )
        else:
            # Disable the overwrite flag if we don't need to overwrite
            overwrite = False

        # save the active state to <name>
        saved_state = PersistentState(Path(self._storage_path, name), missing_ok=True)
        with saved_state.update():
            saved_state.state = self._storage.state

        logger.debug(f"Saved state to {Path(self._storage_path, name)}")
        if not overwrite:
            # add saved state to index
            self._saved_states.add(name)
        return Result(
            "save-state",
            result={Host("coco"): (f"Saved state {name}", 200)},
            type_="FULL",
        )

    async def load_state(self, request: dict = {}):
        """Process the POST request to load a previously saved state.

        Clear the internal state and re-load a state previously saved. Paths under
        `exclude_from_reset` in the config will not be overwritten by this.
        """
        # get request parameters
        name = request.get("name")
        if name not in self._saved_states:
            raise InvalidUsage(
                f"No saved state with name '{name}'. Choose one of: "
                + self._saved_states_list
            )

        excluded = self._backup_excluded_paths()

        # Overwrite our internal storage with a new PersistentState
        self._storage = PersistentState(Path(self._storage_path, name))

        self._recover_excluded_paths(excluded)

        return Result(
            "load-state",
            result={Host("coco"): (f"Loaded state {name}", 200)},
            type_="FULL",
        )

    async def get_saved_states(self, _: dict = {}):
        """Process the GET request to list all saved states.

        Returns a list of previously saved states on disk.
        """
        return Result(
            "saved-states",
            result={Host("coco"): (sorted(self._saved_states), 200)},
            type_="FULL",
        )

    def _backup_excluded_paths(self):
        excluded = {}
        for path in self.exclude_from_reset:
            split_path = path.split("/")
            element = self._storage.state
            for p in split_path:
                try:
                    element = element[p]
                except KeyError as key:
                    logger.debug(
                        f"Can't exclude {key} from config. "
                        f"Path {path} not found in state."
                    )
                    break
            excluded[path] = element
        return excluded

    def _recover_excluded_paths(self, paths):
        for path, content in paths.items():
            with self._storage.update():
                location, new_entry = self._find_new(path)
                location[new_entry] = content


def load_kotekan_config_file(file: str | Path):
    """Load a kotekan config file to json, supporting jinja templates.

    Parameters
    ----------
    file
        Full path to the config file.
    """
    file = Path(file)

    extension = file.suffix
    name = file.stem
    dir = file.parent

    if extension not in {".j2", ".yaml", ".yml"}:
        raise ValueError(
            f"Invalid file type: {extension}. Must be one of [.j2, .yaml, .yml]"
        )

    if extension != ".j2":
        # This is just a yaml file
        with open(file) as fh:
            config_yaml = yaml_load(fh)
    else:
        # This is a jinja template
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(dir), autoescape=jinja2.select_autoescape()
        )
        template = env.get_template(name)
        # Convert to yaml with no extra arguments
        config_yaml = yaml_load(template.render())

    return config_yaml
