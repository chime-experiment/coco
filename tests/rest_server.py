"""A generic REST server used for testing."""

import http.server
import json
import threading
from collections import namedtuple
from http import HTTPStatus

import pytest

__all__ = ["rest_server"]

# Stores route information
Route = namedtuple("Route", ["path", "method", "callback", "response"])

# Stores hit information
Hit = namedtuple("Hit", ["path", "method", "request", "code", "response"])


@pytest.fixture
def rest_server():
    return RestServer


class Handler(http.server.BaseHTTPRequestHandler):
    """Handles requests from the server.

    A new instance of this class is created on every connection.
    """

    def record_hit(self, code, body, response=None):
        """Record a hit on the rest server."""

        # The hit is recorded under the base path
        path = self.path.split("?", 1)[0]
        path = path.split("#", 1)[0]

        # Decode body, if needed
        try:
            body = body.decode()
        except AttributeError:
            pass

        # Pass back up to the RestServer instance
        self.server.rest_server.record_hit(
            path, Hit(self.path, self.command, body, int(code), response)
        )

    def send_json(self, body, response):
        """JSON-encode "response" and send it back."""

        # Send an empty response if not given one
        if response is None:
            self.record_hit(HTTPStatus.NO_CONTENT, body)
            self.send_error(HTTPStatus.NO_CONTENT, body)
            return

        # Record
        self.record_hit(HTTPStatus.OK, body, response)

        # JSON encode
        response = json.dumps(response)

        # Respond with success (=200)
        self.send_response_only(HTTPStatus.OK)

        # Headers
        self.send_header("Server", self.version_string())
        self.send_header("Date", self.date_time_string())
        self.send_header("Connection", "close")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()

        # Response goes in the body
        try:
            self.wfile.write(response.encode())
        except BrokenPipeError:
            pass
        return

    def handle_route(self):
        """Handle a request."""

        # Set to True if a path matches but the method is wrong
        bad_method = False

        # Split the path itself from the query
        query_split = self.path.split("?", 1)
        path = query_split[0]
        query = None
        if len(query_split) > 1:
            query = query_split[1]

        # Split the path from the fragment
        fragment_split = path.split("#", 1)
        path = fragment_split[0]
        fragment = None
        if len(fragment_split) > 1:
            fragment = fragment_split[1]

        # Read the body
        if self.headers["Content-Length"]:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if isinstance(body, bytes):
                body = body.decode()
            body = json.loads(body)
        else:
            body = {}

        # Handle accepting any route
        if self.server.rest_server.any_route:
            if self.server.rest_server.any_callback:
                response = self.server.rest_server.any_callback(path, body)
            else:
                # If no callback, generate a generic response
                response = {}
                if body:
                    response["body"] = body
                if query:
                    response["query"] = query
                if fragment:
                    response["fragment"] = fragment

                # Add generic response data
                response["path"] = path
                response["result"] = "success"

            # Return the response.
            self.send_json(body, response)
            return

        # Not accepting everyhing: find a route for this request
        for route in self.server.rest_server.routes:
            if route.path == path:
                if route.method == self.command:
                    # Handle the route
                    if route.callback:
                        response = route.callback(route, body)
                    else:
                        response = route.response
                    # Return the response.
                    self.send_json(body, response)
                    return
                bad_method = True

        # No matching route.  Send an error
        error_code = (
            HTTPStatus.METHOD_NOT_ALLOWED if bad_method else HTTPStatus.NOT_FOUND
        )
        self.record_hit(error_code, body if body else query)
        self.send_error(error_code)
        return

    # The BaseHTTPRequestHandler separate handling by HTTP command.
    # But we don't need that.
    do_GET = handle_route
    do_POST = handle_route


class RestServer:
    """A generic REST server used for testing.

    Server instances listen on random ephemeral port on 127.0.0.1 meaning
    multiple servers can be used simultaneously, and the server won't get in the
    way of or be blocked by other (real) servers running on the test platform.

    How to use:
    1.  Add routes to the server by calling `add_route`.
    2.  Start the server with `start`.
    3.  Use the "port" attribute to get this port number from the running server.
    4.  Call `shutdown` when finished with the server to ensure it exits cleanly.
    """

    def __init__(self):
        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_port

        # So the Handler can find this instance
        self.server.rest_server = self

        # If True, all routes are accepted
        self.any_route = False

        # If accepting all routes, this will be called to create the return value
        self.any_callback = None

        # List of routes added with add_route
        self.routes = []

        # Dict of routes hit, keyed by path.
        self._hits = {}

        # Server runs in this thread
        self.thread = None

        # Is the server running?
        self.running = False

    def accept_all(self, callback=None):
        """Set up this rest server to accept any endpoint."""
        self.any_route = True
        self.any_callback = callback

    def add_route(self, path, method="GET", callback=None, response=None):
        """Add a route to the server.

        If neither `callback` nor `response` is given, an empty response
        (HTTP status = 204) will be sent back to the client.

        Parameters
        ----------
        path : str
            The route (URL) path
        method : str, optional
            The method for the route.  Defaults to "GET"
        callback : Callable, optional
            A callback to service the route.  The value returned is JSON
            encoded and sent back to the client.
        response : Any, optional
            A response returned to the client, if callback isn't given.
        """
        self.routes.append(
            Route(path=path, method=method, callback=callback, response=response)
        )

    def record_hit(self, route, hit):
        """Record a hit on a route."""

        if route not in self._hits:
            self._hits[route] = [hit]
        else:
            self._hits[route].append(hit)

    def start(self):
        """Start running the server.

        Raises RuntimeError if no routes have been added or if the server is
        already running.
        """
        if not self.routes and not self.any_route:
            raise RuntimeError("No routes for server")
        if self.running:
            raise RuntimeError("Already running")

        self.running = True

        # Create a thread for the server
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True, kwargs={"poll_interval": 0.1}
        )

        # Start it
        self.thread.start()

    def shutdown(self):
        """Stop a running server.

        If the server isn't running, this does nothing.
        """
        if not self.running:
            return

        if self.thread:
            self.server.shutdown()
            self.thread.join()
            self.thread = None

        self.running = False

    # Methods for testing interaction with the server
    def hits(self, route):
        """A list of hits recorded a route.

        If no hits were made, returns an empty list.
        """
        return self._hits.get(route, [])

    def hit_count(self, route):
        """Number of times "route" was hit.

        Equivalent to `len(hits(route))`
        """
        return len(self.hits(route))

    def assert_hit_received(self, route, sent, full=False):
        """Assert that at least one hit of "route" received "sent".

        Parameters
        ----------
        sent : dict
            The expected data that was sent
        full : bool
            If Ture, extra keys may not appear in the received data.
            Defaults to False, meaning a partial match is okay.
        """

        def _compare(a, b, equal, path=""):
            """Check a and b.

            Parameters
            ----------
            a, b: Any
                Items to compare
            equal:
                If False, ignore extra keys in "a".
            path:
                The path to this element.
            """
            display_path = f"in {path}" if path else "at top-level"
            # Fail if element types differ
            if type(a) is not type(b):
                return f"{display_path}: types differ"

            if isinstance(b, dict):
                a_keys = set(a.keys())
                b_keys = set(b.keys())

                if equal and (a_keys ^ b_keys):
                    # Equality requested, but keys are not the same fails
                    return f"{display_path}: extra keys: {a_keys ^ b_keys}"
                if not equal and not (a_keys >= b_keys):
                    # Not equal, but b is not a subset of a
                    return f"{display_path}: missing keys: {b_keys - a_keys}"

                # If the simple checks passed, loop over keys in b
                for key in b_keys:
                    subpath = f'{display_path} -> "{key}"' if path else f'"{key}"'
                    # Fail if any key values fail
                    result = _compare(a[key], b[key], equal, subpath)
                    if result:
                        return result
            elif isinstance(b, list):
                # Fail if lists aren't the same length
                if len(a) != len(b):
                    return f"{display_path}: Bad length ({len(a)} != {len(b)})"

                # Zip the lists together and compare
                for index, items in enumerate(zip(a, b)):
                    subpath = f"{display_path} -> [{index}]" if path else f"[{index}]"
                    result = _compare(*items, equal, subpath)
                    if result:
                        return result
            else:
                # Fail if scalars aren't the same
                if a != b:
                    return f"{display_path}: {a} != {b}"

            # Nothing failed
            return None

        for hit in self.hits(route):
            # Return on first success
            result = _compare(hit.request, sent, full)
            if not result:
                return

        # If no matches were made, fail
        pytest.fail(
            f'Data not received by route "{route}": {result}\n'
            f"Expected\n  {sent}\nReceived:\n   "
            "\n   ".join([str(hit.request) for hit in self.hits(route)])
        )
