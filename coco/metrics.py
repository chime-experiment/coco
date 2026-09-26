"""Metrics aggregator."""

import json
import logging
import signal
import time
import traceback

import redis
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    disable_created_metrics,
    generate_latest,
)

logger = logging.getLogger(__name__)

# Redis connection
redis_conn = None

# Cache of the rendered metrics
rendered = None


def signal_handler(signum, frame):
    """Signal handler."""
    global redis_conn

    logger.debug(f"Caught signal {signum}.  Exiting.")
    if redis_conn:
        redis_conn.close()
        redis_conn = None
    raise KeyboardInterrupt


def init_metrics(all_endpoints):
    """Initialise prometheus metric instances."""
    disable_created_metrics()
    dropped_requests = Counter(
        "coco_dropped_request",
        "Count of requests dropped by coco.",
        ["endpoint"],
    )

    # Init all the dropped requests metrics
    for endpoint in all_endpoints:
        dropped_requests.labels(endpoint=endpoint).reset()

    return {
        "dropped_request": dropped_requests,
        "coco_calls": Counter(
            "coco_calls",
            "Calls forwarded by coco to hosts.",
            ["endpoint", "host", "port", "status"],
        ),
        "qlen": Gauge(
            "coco_queue_length", "Length of queue storing coco requests.", unit="total"
        ),
        "queue_wait_time": Histogram(
            "coco_queue_wait_time",
            "Length of time the request is in the queue before being processed",
            ["endpoint"],
            unit="seconds",
        ),
        "external_response_time": Histogram(
            "coco_external_response_time",
            "Length of time external hosts take to answer coco's requests",
            ["endpoint", "host", "port"],
            unit="seconds",
        ),
    }


def handle_requests(pipe):
    """Handle requests for metrics.

    Parameters
    ----------
    pipe
        The pipe to communicate with the rest of Sanic.
    dirty : bool
        If True, the metrics are dirty (need regeneration)
    """
    global rendered

    # Are there metric requests?
    if pipe.poll():
        # Re-render the metrics, if necessary
        if not rendered:
            rendered = (generate_latest(), CONTENT_TYPE_LATEST)

        # Once we're servicing requests, we handle them all
        while pipe.poll():
            # Discard whatever we were sent
            pipe.recv()

            # Reply with the render
            pipe.send(rendered)


# qlen cache.
_qlen = None


def update_metrics(metrics):
    """Update the coco metrics.

    If any metric is updated, the global "rendered" is reset
    to force re-rendering.

    Parameters
    ----------
    metrics : dict
        The metrics dict created by init_metrics()
    """
    global _qlen, rendered

    # Iterate over all metrics
    for name, metric in metrics.items():
        if name == "dropped_request":
            # Redis list "dropped_requests" has one endpoint per dropped request
            while redis_conn.llen("dropped_requests") > 0:
                rendered = None
                metric.labels(
                    endpoint=redis_conn.lpop("dropped_requests").decode()
                ).inc()
        elif name == "coco_calls":
            while redis_conn.llen("coco_calls") > 0:
                rendered = None
                labels = json.loads(redis_conn.lpop("coco_calls"))
                metric.labels(**labels).inc()
        elif name == "qlen":
            new_qlen = int(redis_conn.llen("queue"))
            if new_qlen != _qlen:
                rendered = None
                metric.set(new_qlen)
                _qlen = new_qlen
        elif name == "queue_wait_time" or name == "external_response_time":
            while redis_conn.llen(name) > 0:
                rendered = None
                labels = json.loads(redis_conn.lpop(name))
                # Extract observed value from the dict
                value = labels.pop("value")
                metric.labels(**labels).observe(value)
        else:
            # Unhandled metric
            logger.warning(f"not updating unknown metric {name!r}")


def aggregator(app, all_endpoints, pipe, port):
    """Sanic worker for aggregating and reporting metrics.

    Parameters
    ----------
    app:
        The controlling Sanic app
    all_endpoints:
        A set of all endpoint names.
    pipe:
        The pipe on which to listen for requests.
    port:
        The redis port
    """

    global redis_conn

    shutdown = False
    logger.debug("metric.aggregator started")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Init
        metrics = init_metrics(all_endpoints)

        # Connect to redis
        redis_conn = redis.Redis(port=port)

        # Do two things forever
        while True:
            update_metrics(metrics)
            handle_requests(pipe)
            time.sleep(1)
    except KeyboardInterrupt:
        # Normal termination
        logger.info("metric.aggregator shutdown")
        shutdown = True
    except SystemExit:
        # Normal exit
        logger.info("qworker shutdown")
        shutdown = False
    except BaseException as e:  # noqa: BLE001
        logger.error(f"metric.aggregator encountered an error: {e}")
        logger.error(traceback.format_exc())
    finally:
        if not shutdown:
            # Shutdown Sanic on abnormal exit
            app.manager.terminate()
