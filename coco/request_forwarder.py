"""Forward requests to a set of hosts."""
import aiohttp
import json

from . import TaskPool
from . import Result


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

    @staticmethod
    async def _request(session, method, host, endpoint, request):
        url = host + endpoint
        try:
            async with session.request(
                method,
                url,
                data=json.dumps(request),
                raise_for_status=False,
                timeout=aiohttp.ClientTimeout(1),
            ) as response:
                return host, (await response.json(), response.status)
        except BaseException as e:
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
            ret = dict(await tasks.join())

        return Result(name, ret)
