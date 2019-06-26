"""Forward requests to a set of hosts."""
import aiohttp
import json
import redis
from prometheus_client import Counter

from . import TaskPool
from .metric import format_metric_label, format_metric_name, start_metrics_server


class RequestForwarder:
    """Take requests and forward to a given set of hosts."""

    def __init__(self):
        self._endpoints = dict()
        self._groups = dict()
        self.session_limit = 1

    def set_session_limit(self, session_limit):
        """
        Set session limit.

        The session limit is the maximum of concurrent tasks when forwarding requests. Set low
        for lower memory usage.

        Parameters
        ----------
        session_limit : int
            Number of maximum tasks being executed concurrently by request forwarder.
        """
        self.session_limit = session_limit

    def add_group(self, name, hosts):
        """
        Add a group of hosts.

        Parameters
        ----------
        name : str
            Name of the group.
        hosts : list of str
            Hosts in the group. Expected to have format "http://hostname:port/"
        """
        self._groups[name] = hosts

    def add_endpoint(self, name, endpoint):
        """
        Add an endpoint.

        Parameters
        ----------
        name : str
            Name of the endpoint.
        endpoint : :class:`Endpoint`
            Endpoint instance.
        """
        self._endpoints[name] = endpoint

    def start_prometheus_server(self, port):
        """
        Start prometheus server.

        Parameters
        ----------
        port : int
            Server port.
        """
        # Conect to redis
        self.redis_conn = redis.Redis(host='localhost', port=6379, db=0)

        def fetch_request_count():
            for edpt in self._endpoints:
                # Get current count and reset to 0
                incr = int(self.redis_conn.getset(f"request_counter_{edpt}", "0"))
                self.request_counter.labels(endpoint=edpt).inc(incr)

        start_metrics_server(port, callbacks=[fetch_request_count])

    def init_metrics(self):
        """
        Initialise counters for every prometheus endpoint.
        """
        # TODO: change description/name to dropped requests once that is in place
        self.request_counter = Counter(
            format_metric_name(f"coco_requests"),
            "Count of requests received by coco.",
            ["endpoint"],
            unit="total"
        )
        self.result_counter = Counter(
            format_metric_name(f"coco_results"),
            "Result of requests forwarded by coco.",
            ["endpoint", "host", "port", "status"],
            unit="total",
        )
        for edpt in self._endpoints:
            for grp in self._groups:
                for h in self._groups[grp]:
                    self.request_counter.labels(endpoint=edpt).inc(0)
                    label, port = format_metric_label(h)
                    self.result_counter.labels(endpoint=edpt, host=label,
                                               port=port, status="200").inc(0)
                    self.result_counter.labels(endpoint=edpt, host=label,
                                               port=port, status="0").inc(0)

    async def call(self, name, request):
        """
        Call an endpoint.

        Parameters
        ----------
        name : str
            Name of the endpoint.
        request : dict
            Request data.

        Returns
        -------
        :class:`Result`
            Reply of endpoint call.
        """
        return await self._endpoints[name].call(request)

    async def _request(self, session, method, host, endpoint, request):
        url = host + endpoint
        host_label, port = format_metric_label(host)
        try:
            async with session.request(
                method,
                url,
                data=json.dumps(request),
                raise_for_status=False,
                timeout=aiohttp.ClientTimeout(1),
            ) as response:
                self.result_counter.labels(
                    endpoint=endpoint, host=host_label, port=port, status=str(response.status)
                ).inc()
                try:
                    return host, (await response.json(content_type=None), response.status)
                except json.decoder.JSONDecodeError:
                    return host, (await response.text(content_type=None), response.status)
        except BaseException as e:
            print(endpoint)
            self.result_counter.labels(
                endpoint=endpoint, host=host_label, port=port, status="0"
            ).inc()
            return host, (str(e), 0)

    async def forward(self, name, group, method, request):
        """
        Forward an endpoint call.

        Parameters
        ----------
        name : str
            Name of the endpoint.
        request : dict
            Request data to forward.

        Returns
        -------
        :class:`Result`
            Result of the endpoint call.
        """
        hosts = self._groups[group]

        connector = aiohttp.TCPConnector(limit=0)
        async with aiohttp.ClientSession(connector=connector) as session, TaskPool(
            self.session_limit
        ) as tasks:
            for host in hosts:
                await tasks.put(self._request(session, method, host, name, request))
            return dict(await tasks.join())
