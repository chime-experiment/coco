"""Forward requests to a set of hosts."""
from asyncio import TimeoutError
import copy
import os
import json
from typing import Iterable

import aiohttp
import redis
from prometheus_client import Counter, Gauge, Histogram

from . import TaskPool
from .metric import start_metrics_server
from .util import Host
from .blacklist import Blacklist
from .result import Result


class Forward:
    """Keep data about a forward to another endpoint."""

    def __init__(self, name, group=None, request=None, check=None):
        self.name = name
        self.request = request
        self.group = group
        self.check = check
        if not self.request:
            self.request = dict()

    async def trigger(self, method, request=None, hosts=None, params=[]):
        """
        Trigger the forwarding.

        Parameters
        ----------
        method : str
            Request method. FIXME: this is ignored.
        request : dict
            (optional) The :class:`Forward`'s `request` gets added to this (overwriting any duplicate values),
            and send with the forward call.
        hosts : str or List(str)
            (optional) The group or host(s) to forward to. If not supplied, the value set in the constructor is used.
        params : list of (key, value) pairs
            URL query parameters to forward to target endpoint.

        Returns
        -------
        Tuple[bool, :class:`Result`]
            (False if any check failed. True otherwise., Result of the Forward.)
        """
        if self.request:
            if not request:
                request = dict()
            request = copy.copy(request)
            request.update(self.request)
        if not hosts:
            hosts = self.group
        forward_result = await self.forward_function(
            self.name, method, request, hosts, params
        )
        if self.check:
            for check in self.check:
                forward_result.success &= await check.run(forward_result)

        return forward_result

    def forward_function(self, **kwargs):
        """Pure virtual method, only use overwriting methods from sub classes."""
        raise NotImplementedError(
            "The Forward base class should not be used itself, Use "
            "CocoForward or ExternalForward instead and pass a forwarder to "
            "it."
        )

    def _save_result(self, result, addition):
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
            self.forward_function = forwarder.internal
        super().__init__(name, group, request, check)


class ExternalForward(Forward):
    """Keep data about a forward to an external endpoint."""

    def __init__(self, name, forwarder, group, request=None, check=None):
        if forwarder:
            self.forward_function = forwarder.external
        super().__init__(name, group, request, check)


class RequestForwarder:
    """Take requests and forward to a given set of hosts.

    Parameters
    ----------
    blacklist_path
        The file we should store the blacklist in.
    """

    def __init__(self, blacklist_path: os.PathLike, timeout: int):
        self._endpoints = dict()
        self._groups = dict()
        self.session_limit = 1
        self.blacklist = Blacklist([], blacklist_path)
        self.timeout = timeout

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
        self.redis_conn = redis.Redis(host="127.0.0.1", port=6379, db=0)

        def fetch_request_count():
            for edpt in self._endpoints:
                # Get current count and reset to 0
                incr = int(self.redis_conn.getset(f"dropped_counter_{edpt}", "0"))
                self.dropped_counter.labels(endpoint=edpt).inc(incr)

        def fetch_queue_len():
            self.queue_len.set(int(self.redis_conn.llen("queue")))

        start_metrics_server(port, callbacks=[fetch_request_count, fetch_queue_len])

    def init_metrics(self):
        """Initialise counters for every prometheus endpoint."""
        self.dropped_counter = Counter(
            "coco_dropped_request",
            "Count of requests dropped by coco.",
            ["endpoint"],
            unit="total",
        )
        self.call_counter = Counter(
            "coco_calls",
            "Calls forwarded by coco to hosts.",
            ["endpoint", "host", "port", "status"],
            unit="total",
        )
        self.queue_len = Gauge(
            "coco_queue_length", f"Length of queue storing coco requests.", unit="total"
        )
        self.queue_wait_time = Histogram(
            "coco_queue_wait_time",
            "Length of time the request is in the queue before being processed",
            ["endpoint"],
            unit="seconds",
        )
        for edpt in self._endpoints:
            self.dropped_counter.labels(endpoint=edpt).inc(0)
            self.redis_conn.set(f"dropped_counter_{edpt}", "0")

    async def internal(self, name, method, request, hosts=None, params=[]):
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
        params : list of (key, value) pairs
            This argument is ignored but needs to be included to maintain compatibility with
            other forwards.

        Returns
        -------
        :class:`Result`
            Reply of endpoint call.
        """
        # the request data gets popped in endpoint.call(), so we give them a copy only
        request = copy.copy(request)
        return await self._endpoints[name].call(request=request, hosts=hosts)

    async def _request(self, session, method, host, endpoint, request, params):
        url = host.join_endpoint(endpoint)
        hostname, port = host.hostname, host.port
        try:
            async with session.request(
                method,
                url,
                json=request,
                raise_for_status=False,
                timeout=aiohttp.ClientTimeout(self.timeout),
                params=params,
            ) as response:
                self.call_counter.labels(
                    endpoint=endpoint,
                    host=hostname,
                    port=port,
                    status=str(response.status),
                ).inc()
                try:
                    return (
                        host,
                        (await response.json(content_type=None), response.status),
                    )
                except json.decoder.JSONDecodeError:
                    return host, (await response.text(), response.status)
        except TimeoutError:
            self.call_counter.labels(
                endpoint=endpoint, host=hostname, port=port, status="0"
            ).inc()
            return host, ("Timeout", 0)
        except BaseException as e:
            self.call_counter.labels(
                endpoint=endpoint, host=hostname, port=port, status="0"
            ).inc()
            return host, (str(e), 0)

    async def external(self, name, method, request, group, params=[]):
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
        params : list of (key, value) pairs
            URL query parameters to forward to target endpoint.

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
                    await tasks.put(
                        self._request(session, method, host, name, request, params)
                    )
            return Result(name, dict(await tasks.join()))
