"""Forward requests to a set of hosts."""
from asyncio import TimeoutError
import aiohttp
import os
import json
from typing import Iterable

import aiohttp
import redis
from prometheus_client import Counter

from . import TaskPool
from .metric import start_metrics_server
from .util import Host
from .blacklist import Blacklist


class RequestForwarder:
    """Take requests and forward to a given set of hosts.

    Parameters
    ----------
    blacklist_path
        The file we should store the blacklist in.
    """

    def __init__(self, blacklist_path: os.PathLike):
        self._endpoints = dict()
        self._groups = dict()
        self.session_limit = 1
        self.blacklist = Blacklist([], blacklist_path)

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

    def add_group(self, name: str, hosts: Iterable[Host]):
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
        self.blacklist.add_known_hosts(self._groups[name])

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
        self.redis_conn = redis.Redis(host="localhost", port=6379, db=0)

        def fetch_request_count():
            for edpt in self._endpoints:
                # Get current count and reset to 0
                incr = int(self.redis_conn.getset(f"request_counter_{edpt}", "0"))
                self.request_counter.labels(endpoint=edpt).inc(incr)

        start_metrics_server(port, callbacks=[fetch_request_count])

    def init_metrics(self):
        """Initialise counters for every prometheus endpoint."""
        # TODO: change description/name to dropped requests once that is in place
        self.request_counter = Counter(
            "coco_requests", "Count of requests received by coco.", ["endpoint"], unit="total"
        )
        self.call_counter = Counter(
            "coco_calls",
            "Calls forwarded by coco to hosts.",
            ["endpoint", "host", "port", "status"],
            unit="total",
        )
        for edpt in self._endpoints:
            self.request_counter.labels(endpoint=edpt).inc(0)
            self.redis_conn.set(f"request_counter_{edpt}", "0")

    async def call(self, name, request, hosts=None):
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
        return await self._endpoints[name].call(request, hosts)

    async def _request(self, session, method, host, endpoint, request):
        url = host.join_endpoint(endpoint)
        hostname, port = host.hostname, host.port
        try:
            async with session.request(
                method,
                url,
                json=request,
                raise_for_status=False,
                timeout=aiohttp.ClientTimeout(10),
            ) as response:
                self.call_counter.labels(
                    endpoint=endpoint, host=hostname, port=port, status=str(response.status)
                ).inc()
                try:
                    return host, (await response.json(content_type=None), response.status)
                except json.decoder.JSONDecodeError:
                    return host, (await response.text(), response.status)
        except TimeoutError:
            self.call_counter.labels(endpoint=endpoint, host=hostname, port=port, status="0").inc()
            return host, ("Timeout", 0)
        except BaseException as e:
            self.call_counter.labels(endpoint=endpoint, host=hostname, port=port, status="0").inc()
            return host, (str(e), 0)

    async def forward(self, name, group, method, request):
        """
        Forward an endpoint call.

        Parameters
        ----------
        name : str
            Name of the endpoint.
        group : str or list(Host)
            Hosts to forward to.
        method : str
            HTTP method.
        request : dict
            Request data to forward.

        Returns
        -------
        :class:`Result`
            Result of the endpoint call.
        """
        if isinstance(group, str):
            hosts = self._groups[group]
        else:
            hosts = group

        connector = aiohttp.TCPConnector(limit=0)
        async with aiohttp.ClientSession(connector=connector) as session, TaskPool(
            self.session_limit
        ) as tasks:
            for host in hosts:
                if host not in self.blacklist.hosts:
                    await tasks.put(self._request(session, method, host, name, request))
            return dict(await tasks.join())
