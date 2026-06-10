"""pytest fixture to run the coco daemon and client."""

import json
import multiprocessing
import threading
from time import sleep

import fakeredis
import pytest
import yaml

from coco import config

__all__ = ["coco_runner"]


# Can't use pyfakefs here, so we rely on tmp_path instead
@pytest.fixture
def coco_runner(tmp_path, rest_server):
    """Yields a function to create a CocoRunner.

    Arguments to the returned function are passed to the CocoRunner
    constructor, except for "arena", which is ignored, if given.

    Ensures the coco runner has stopped after the test completes.
    """

    # The runner instance is stored here
    runner = None

    def _create_runner(config={}, **kwargs):
        nonlocal tmp_path, rest_server, runner

        # Add the fixtures to kwargs, overwriting the caller's
        # values if given
        kwargs["arena"] = tmp_path
        kwargs["rest_server"] = rest_server

        if runner is None:
            runner = CocoRunner(**kwargs)

        return runner

    yield _create_runner

    # Ensure runner terminates
    if runner:
        runner.stop()


def _daemon_main(conf_path, args, pipe):
    """This is the daemon process entry point."""
    import traceback

    from click.testing import CliRunner

    from coco.core import cocod

    print(f"Invoking cocod from {conf_path}")

    # Invoke
    result = CliRunner().invoke(cocod, args, env={"COCO_CONFIG_FILE": conf_path})

    # Show traceback if one was created
    if (
        result.exit_code
        and result.exc_info
        and type(result.exception) is not SystemExit
    ):
        traceback.print_exception(*result.exc_info)

    # Print output so it appears in the test log on failure
    print(result.output)

    # Convert the result to something that can be pickled and send
    # it over the pipe
    result_dict = {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if result.exception:
        result_dict["exception_type"] = type(result.exception)
        result_dict["exception_text"] = str(result.exception)
    else:
        result_dict["exception_type"] = None
        result_dict["exception_text"] = None
    pipe.send(result_dict)


class CocoRunner:
    """Runs the coco daemon and client.

    The daemon is run in a subprocess (not a thread, because Sanic doesn't work
    like that).

    Attributes
    ----------
    arena : pathlib.Path
        An empty temporary directory to be used by cocod
    rest_server : callable
        The rest_server fixture
    no_daemon : bool
        If True, don't start the daemon before invoking the client.  It
        can still be started manually by calling `start_daemon`.
    daemon_args : list, optional
        Command-line arguments to the daemon, if any.  The "--testing" flag
        will always be appended to these arguments and does not need to be
        listed here.
    """

    def __init__(self, *, arena, rest_server, no_daemon=False, daemon_args=[]):
        self.rest_server = rest_server
        self.no_daemon = no_daemon

        # Populate the arena
        self.storage_path = arena / "storage"
        self.storage_path.mkdir(mode=0o700)
        self.blocklist = arena / "blocklist.json"
        with self.blocklist.open(mode="w") as f:
            f.write("{}")
        self.endpoint_dir = arena / "endpoints"
        self.endpoint_dir.mkdir(mode=0o700)
        self.config_file = arena / "coco.conf"

        # Config.  We'll write it to disk just before starting the daemon
        self.config = {
            "host": "127.0.0.1",
            "port": 0,  # Overridden by --testing
            "log_level": "DEBUG",
            "blocklist_path": str(self.blocklist),
            "storage_path": str(self.storage_path),
            "endpoint_dir": str(self.endpoint_dir),
            "groups": {},
            "comet_broker": {"enabled": False},
        }

        # Process for coco daemon
        self._daemon_proc = None

        # Arguments for the daemon
        self._daemon_args = ["--testing", *daemon_args]
        self._daemon_port = None

        # Return value from the daemon
        self._daemon_result = None

        # Pipe for the daemon to send a result back to the caller
        pipe = multiprocessing.Pipe(duplex=False)
        self._daemon_recv = pipe[0]
        self._daemon_send = pipe[1]

        # fakeredis server and its thread
        self._redis_server = None
        self._redis_thread = None
        self._redis_port = None

        # Rest server farm
        self._farm = []

    def add_config(self, **extra_config):
        """Update the daemon's config.

        Must be called before starting the daemon.
        """
        if self._daemon_proc:
            raise RuntimeError("called after start_daemon")

        # Merge in config
        self.config = config.merge_dict_tree(self.config, extra_config)

    def add_targets(self, group, count):
        """Add `count` target rest servers to the group `group`.

        The targets are created using the rest_server test fixture.
        The targets will be added to the coco group `group`.

        Must be called before starting the daemon.  The servers
        themselves are stored internally so they can be stopped by
        the stop() method.

        Returns the actual list of targets created
        """
        if self._daemon_proc:
            raise RuntimeError("called after start_daemon")

        # Create the targets
        targets = []
        for _ in range(count):
            server = self.rest_server()
            server.accept_all()
            server.start()

            # Remember it so we can stop it later
            self._farm.append(server)

            # Record port
            targets.append(f"127.0.0.1:{server.port}")

        # merge_dict_tree will do all the work for us updating the config
        self.add_config(groups={group: targets})

        return targets

    def add_endpoint(self, name, endpoint_def):
        """Add an endpoint to the daemon.

        Be sure to also add the target group to the config with `add_group`,
        if you want things to work.

        Must be called before starting the daemon.
        """

        if self._daemon_proc:
            raise RuntimeError("called after start_daemon")

        # Dump to endpoint file
        with open(self.endpoint_dir / f"{name}.conf", "w") as f:
            yaml.dump(endpoint_def, f)

    def _start_redis(self):
        """Start a thread running a fakeredis server."""

        # If it's already running, do nothing
        if self._redis_thread and self._redis_thread.is_alive():
            return self._redis_port

        # Bind the server to an ephemeral port
        self._redis_server = fakeredis.TcpFakeServer(
            ("127.0.0.1", 0), server_type="redis"
        )

        # Retrieve the bound port
        self._redis_port = self._redis_server.server_address[1]

        # Start accepting connections in a separate thread
        self._redis_thread = threading.Thread(
            target=self._redis_server.serve_forever, daemon=True
        )
        self._redis_thread.start()

        # return the port
        return self._redis_port

    def start_daemon(self):
        """Start function for the coco daemon.  Runs in a subprocess."""

        # If it's already running, do nothing
        if self._daemon_proc:
            return

        # If the daemon was already stopped, do nothing
        if self._daemon_result:
            return

        # Start redis before starting the daemon.  If the fakeredis
        # server is already running, somehow, this does nothing.
        redis_port = self._start_redis()

        # Add the redis port to the config
        self.add_config(redis_port=redis_port)

        # Write the config
        with self.config_file.open(mode="w") as f:
            yaml.dump(self.config, f)

        # Get multiproc context
        context = multiprocessing.get_context("spawn")

        # Create a daemon subprocess
        self._daemon_proc = context.Process(
            target=_daemon_main,
            args=(str(self.config_file), self._daemon_args, self._daemon_send),
        )

        # Start it
        self._daemon_proc.start()

        # Wait for the daemon to create the _TESTING talkback (or crash)
        testing_file = self.storage_path / "_TESTING"
        while self._daemon_proc.is_alive():
            try:
                with testing_file.open(mode="r") as f:
                    self._daemon_port = int(json.load(f)["port"])
                return
            except OSError:
                # Try again next time.
                pass
            finally:
                # This is in a finally block because we want to wait a bit
                # even after it successfully fetches the port.
                sleep(0.2)

    def invoke(self, args):
        """Invoke the coco client.

        Parameters
        ----------
        args : list
            Arguments to the coco client.
        """
        raise NotImplementedError("coco not supported yet!")

    def stop(self):
        """Stop the daemon."""

        # Already done?
        if self._daemon_result:
            return self._daemon_result

        if self._daemon_proc:
            while self._daemon_proc.is_alive():
                self._daemon_proc.terminate()
                self._daemon_proc.join()
            self._daemon_proc = None

            # Fetch the result from the pipe, if present
            if self._daemon_recv.poll():
                self._daemon_result = self._daemon_recv.recv()

        # Stop the rest server target farm
        for server in self._farm:
            server.shutdown()

        # Also stop the redis server now
        if self._redis_thread:
            self._redis_server.shutdown()
            self._redis_server.server_close()
            while self._redis_thread.is_alive():
                self._redis_thread.join()
            self._redis_thread = None
            self._redis_server = None

        # Assert non-failure
        if self._daemon_result:
            assert self._daemon_result["exit_code"] == 0, (
                f"Daemon exited with error: {self._daemon_result['exit_code']}"
            )

        # return the daemon result
        return self._daemon_result
