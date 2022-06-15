"""
Endpoint farm for testing coco.

Simulates multiple hosts with endpoints.
"""
import os
import socket
from contextlib import closing
from multiprocessing import Manager, Process

from flask import Flask, request, jsonify
from werkzeug.exceptions import BadRequest


app = Flask(__name__)


@app.route("/<name>")
def endpoint(name):
    """Accept any endpoint call."""
    # Increment or create a counter
    try:
        app.counter[name] += 1
    except KeyError:
        app.counter[name] = 1

    try:
        reply = dict(request.json)
    except BadRequest:
        app.logger.info(
            "Did not get a JSON message, using the empty {}"
        )  # pylint: disable=E1101
        reply = {}

    if request.args:
        reply.update({"params": request.args})

    if name in app.callbacks:
        reply = app.callbacks[name](reply)

    return jsonify(reply)


def find_free_port():
    """Return an unused port."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def flask_start(port, counter, callbacks):
    """Run a flask web server."""
    app.counter = counter
    app.callbacks = callbacks
    app.run(port=port, debug=True, use_reloader=False)


class Farm:
    """
    Endpoint farm.

    Run many flask webservers accepting endpoint calls and counting them for test
    purposes. Count all endpoint calls.

    Parameters
    ----------
    ports : int
        Number of webservers to start with different ports.
    callbacks : dict
        Names of the endpoints and functions they should call.
    """

    def __init__(self, ports, callbacks):
        self._manager = Manager()
        self._counters = {}
        self._processes = []

        self.ports = []

        # Tell flask that this is not a prod environment
        os.environ["FLASK_ENV"] = "development"

        for _ in range(ports):
            port = find_free_port()
            counter = self._manager.dict()

            print(f"Started new process for test endpoints on port {port}.")

            p = Process(target=flask_start, args=(port, counter, callbacks))
            p.start()

            self.ports.append(port)
            self._counters[port] = counter
            self._processes.append(p)

    def __del__(self):
        """
        Destructor.

        Stop the farm.
        """
        for p in self._processes:
            p.terminate()
        self._manager.shutdown()

    def counters(self):
        """Return endpoint call counters."""
        return {port: dict(c) for port, c in self._counters.items()}

    @property
    def hosts(self):
        """Return a list of host names (e.g. "http://localhost:1234/")."""
        hosts = []
        for port in self.ports:
            hosts.append("http://localhost:" + str(port) + "/")
        return hosts
