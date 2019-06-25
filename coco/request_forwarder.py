"""Forward requests to a set of hosts."""
import aiohttp
import json
from prometheus_client import Counter, start_http_server

from . import TaskPool
from . import Result
from .metric import format_metric_label, format_metric_name


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

    # We need a separate server to track metrics produced by this process.
    # This should be called by the worker process when it is started.
    @staticmethod
    def start_prometheus_server(port):
        """
        Start prometheus server.

        Parameters
        ----------
        port : int
            Server port.
        """
        start_http_server(port)

    def init_metrics(self):
        """
        Initialise success/failure counters for every prometheus endpoint.
        """
        self.request_counter = {}
        for edpt in self._endpoints:
            cnt = Counter(format_metric_name(f"coco_{edpt}_result"),
                          "Result of requests forwarded by coco.",
                          ["host", "port", "status"], unit="total")
            for grp in self._groups:
                for h in self._groups[grp]:
                    label, port = format_metric_label(h)
                    cnt.labels(host=label, port=port, status="200").inc(0)
            self.request_counter[edpt] = cnt

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
                self.request_counter[endpoint].labels(host=host_label, port=port,
                                                      status=str(response.status)).inc()
                try:
                    return host, (await response.json(content_type=None), response.status)
                except json.decoder.JSONDecodeError:
                    return host, (await response.text(content_type=None), response.status)
        except BaseException as e:
            self.request_counter[endpoint].labels(host=host_label, port=port,
                                                  status="0").inc()
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
