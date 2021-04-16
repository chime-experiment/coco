"""
coco metric module.

Helper functions for prometheus metric exporting.
"""

import logging
import threading

import aiohttp
from prometheus_client.exposition import (
    MetricsHandler,
    choose_encoder,
    _ThreadingSimpleServer,
    REGISTRY,
)
from prometheus_client.parser import text_string_to_metric_families

from .exceptions import InternalError

logger = logging.getLogger(__name__)


class CallbackMetricsHandler(MetricsHandler):
    """
    Derivative of `prometheus_client.exposition.MetricsHandler`.

    Allows callback functions to be executed when metrics are requested.
    """

    callbacks = []

    def do_GET(self):
        """Respond to request for metrics."""
        for cb in self.callbacks:
            cb()
        registry = self.registry
        encoder, content_type = choose_encoder(self.headers.get("Accept"))
        try:
            output = encoder(registry)
        except Exception as err:
            logger.debug(f"Error generating metric output: {err}")
            self.send_error(500, "error generating metric output")
            raise
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(output)


def start_metrics_server(port, callbacks=None, addr=""):
    """Based on `prometheus_client.exposition.start_http_server` using custom handler."""
    handler = CallbackMetricsHandler.factory(REGISTRY)
    if callbacks is not None:
        handler.callbacks += callbacks
    httpd = _ThreadingSimpleServer((addr, port), handler)
    t = threading.Thread(target=httpd.serve_forever)
    t.daemon = True
    t.start()


async def get(name, port, host="127.0.0.1"):
    """
    Get the value of a metric by requesting it from the prometheus web server.

    Parameters
    ----------
    name : str
        Name of the metric
    port : int
        Port of the prometheus server
    host : str
        Host running the prometheus server (default "127.0.0.1")

    Returns
    -------
    Value of the metric
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://{host}:{port}") as resp:
            resp.raise_for_status()
            metrics = await resp.text()
    for family in text_string_to_metric_families(metrics):
        if family.name == name:
            return family.samples[0].value
    raise InternalError(
        f"Couldn't find metric {name} in response from coco's prometheus client."
    )
