"""Forward requests to a set of hosts."""
from asyncio import TimeoutError
import copy
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


class Forward:
    """Keep data about a forward to another endpoint."""

    def __init__(self, name, group, request=None, check=None):
        self.name = name
        self.request = request
        self.group = group
        self.check = check
        if not self.request:
            self.request = dict()

    def trigger(self, request=None, method="GET", hosts=None):
        """
        Trigger the forwarding.

        Parameters
        ----------
        request : dict
            The :class:`Forward`'s `request` gets added to this (overwriting any duplicate values),
            and send with the forward call.

        Returns
        -------
        :class:`Result`
            The result of the forward call.
        """
        if self.request:
            if not request:
                request = dict()
            request = copy.copy(request)
            request.update(self.request)
        return self.forward_function(self.name, method, request, hosts)

    def forward_function(self, **kwargs):
        """Pure virtual method, only use overwriting methods from sub classes."""
        raise NotImplementedError(
            "The Forward base class should not be used itself, Use "
            "CocoForward or ExternalForward instead and pass a forwarder to "
            "it."
        )


class CocoForward(Forward):
    """Keep data about a forward to another coco endpoint."""

    def __init__(self, name, forwarder, group=None, request=None, check=None):
        if forwarder:
            self.forward_function = forwarder.call
        super().__init__(name, group, request, check)

    async def trigger(self, result, method, request=None, hosts=None):
        """
        Trigger the forward.

        Parameters
        ----------
        result : :class:`Result`
            Result to embed the result of the forward in.
        method : str
            HTTP request method.
        request : dict
            Request data for the forward. Values can be overwritten to `request` configured with
            the forward.
        hosts : str or list(str)
            Hosts(s) to limit the call to.

        Returns
        -------
        bool
            True if forward successful.
        """
        r = await super().trigger(request, method, hosts)
        result.embed(self.name, r)
        return True


class ExternalForward(Forward):
    """Keep data about a forward to an external endpoint."""

    def __init__(self, name, forwarder, group, request=None, check=None):
        if forwarder:
            self.forward_function = forwarder.forward
        super().__init__(name, group, request, check)

    async def trigger(self, result, method, request=None, hosts=None):
        """
        Trigger the forward.

        Parameters
        ----------
        result : :class:`Result`
            Result to embed the result of the forward in.
        method : str
            HTTP request method.
        request : dict
            Request data for the forward. Values can be overwritten to `request` configured with
            the forward.
        hosts : str or list(str)
            Hosts(s) to limit the call to.

        Returns
        -------
        bool
            True if forward successful, False if any of the configured checks failed.
        """
        if hosts is None:
            hosts = self.group
        r = await super().trigger(request, method, hosts)
        if not self.check:
            success = True
        else:
            success = await self.check(self.name, r, result)
        result.add_result(self.name, r)
        return success


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
                incr = int(self.redis_conn.getset(f"dropped_counter_{edpt}", "0"))
                self.dropped_counter.labels(endpoint=edpt).inc(incr)

        start_metrics_server(port, callbacks=[fetch_request_count])

    def init_metrics(self):
        """Initialise counters for every prometheus endpoint."""
        self.dropped_counter = Counter(
            "coco_dropped", "Count of requests dropped by coco.", ["endpoint"], unit="total"
        )
        self.call_counter = Counter(
            "coco_calls",
            "Calls forwarded by coco to hosts.",
            ["endpoint", "host", "port", "status"],
            unit="total",
        )
        for edpt in self._endpoints:
            self.dropped_counter.labels(endpoint=edpt).inc(0)
            self.redis_conn.set(f"dropped_counter_{edpt}", "0")

    async def call(self, name, method, request, hosts=None):
        """
        Call an endpoint.

        Parameters
        ----------
        name : str
            Name of the endpoint.
        method : str
            HTTP method.
        request : dict
            Request data.
        hosts : str or list(Host)
            Hosts to forward to.

        Returns
        -------
        :class:`Result`
            Reply of endpoint call.
        """
        return await self._endpoints[name].call(request=request, hosts=hosts)

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
                    return (host, (await response.json(content_type=None), response.status))
                except json.decoder.JSONDecodeError:
                    return host, (await response.text(), response.status)
        except TimeoutError:
            self.call_counter.labels(endpoint=endpoint, host=hostname, port=port, status="0").inc()
            return host, ("Timeout", 0)
        except BaseException as e:
            self.call_counter.labels(endpoint=endpoint, host=hostname, port=port, status="0").inc()
            return host, (str(e), 0)

    async def forward(self, name, method, request, group):
        """
        Forward an endpoint call.

        Parameters
        ----------
        name : str
            Name of the endpoint.
        method : str
            HTTP method.
        request : dict
            Request data to forward.
        group : str or list(Host)
            Hosts to forward to or group name.

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
