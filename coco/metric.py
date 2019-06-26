"""
coco metric module.

Helper functions for prometheus metric exporting.
"""

import re
import threading
from prometheus_client.exposition import (
    MetricsHandler,
    choose_encoder,
    _ThreadingSimpleServer,
    REGISTRY,
)


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
        except:
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
