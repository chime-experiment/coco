"""coco checks."""

import logging
from pydoc import locate
from typing import Dict

from . import Result

logger = logging.getLogger(__name__)


class Check:
    """
    Base class for coco checks.

    The result of a check is what defines the success of a coco endpoint call.
    """

    def __init__(self, name, on_failure, save_to_state, forwarder, state):
        self._name = name
        if on_failure:
            self.on_failure_call = on_failure.get("call", None)
            self.on_failure_call_single_host = on_failure.get("call_single_host", None)
        else:
            self.on_failure_call = None
            self.on_failure_call_single_host = None
        self.save_to_state = save_to_state
        self.forwarder = forwarder
        self.state = state

    @property
    def name(self):
        """
        Get the name of this result.

        Returns
        -------
        str
            Name
        """
        return self._name

    def run(self, reply):
        """Run the check."""
        raise NotImplementedError(
            f"Function 'run()' is not implemented here. " f"You should use a sub class instead."
        )

    async def on_failure(self, hosts=None):
        """
        Run any on_failure actions.

        Parameters
        ----------
        hosts : list
            (optional) Limit the actions to the given hosts.

        Returns
        -------
        :class:`Result`
            The result of the action.
        """
        if not (self.on_failure_call_single_host or self.on_failure_call):
            return None
        result = Result("on_failure")
        if self.on_failure_call:
            logger.debug(f"Calling {self.on_failure_call} because {self._name} failed.")
            result.embed(
                self.on_failure_call, await self.forwarder.internal(self.on_failure_call, "", {})
            )
        if self.on_failure_call_single_host:
            logger.debug(
                f"Calling {self.on_failure_call_single_host} on hosts "
                f"{hosts} because {self._name} failed."
            )
            result.embed(
                self.on_failure_call_single_host,
                await self.forwarder.internal(self.on_failure_call_single_host, "", {}, hosts),
            )
        return result

    def _save_reply(self, reply):
        """
        Save a forward call reply to state.

        The replies of different hosts get merged.

        Parameters
        ----------
        reply : dict
            Keys are hosts and values are tuples of replies (dict) and HTTP status codes.
        """
        if not self.save_to_state:
            return
        merged = dict()
        for r in reply.values():
            if isinstance(r[0], dict):
                merged.update(r[0])
        self.state.write(self.save_to_state, merged)


class ReplyCheck(Check):
    """Check on a reply."""

    def __init__(self, name, on_failure, save_to_state, forwarder, state):
        super().__init__(name, on_failure, save_to_state, forwarder, state)

    def run(self, reply):
        """
        Run the check on the given reply.

        Parameters
        ----------
        reply : dict
            The reply to check: A tuple of (status code, result) per host.
        """
        super().run(reply)


class IdenticalReplyCheck(ReplyCheck):
    """Check if replies from all hosts are identical."""

    def __init__(self, name, valnames, on_failure, save_to_state, forwarder, state):
        super().__init__(name, on_failure, save_to_state, forwarder, state)
        self.identical_values = valnames

    async def run(self, result: Result):
        """
        Run the check on the given reply.

        Parameters
        ----------
        reply : dict
            The reply to check: A tuple of (status code, result) per host.

        Return
        ------
        bool
            True if the check passed, otherwise False.
        """
        reply = dict()
        for r in result.results.values():
            reply.update(r)

        for valname in self.identical_values:
            gather = list()
            for r in reply.values():
                if isinstance(r, dict):
                    gather.append(r.get(valname, None))
                else:
                    gather.append(r)
            unique_values = set(gather)  # [r.get(valname, None) for r in reply.values()])
            if len(unique_values) > 1:
                logger.warn(
                    f"/{self._name}: Replies from hosts not identical (found "
                    f"{len(unique_values)} unique values for {valname})."
                )
                logger.info(
                    f"Found {len(unique_values)} unique replies for {valname}:\n"
                    f"{unique_values}"
                )
                for host in reply.keys():
                    result.report_failure(self._name, host, "not_identical", "all")
                result.embed(self._name, await self.on_failure())
                return False
        self._save_reply(reply)
        return True


class ValueReplyCheck(ReplyCheck):
    """Check for certain values in the replies."""

    def __init__(self, name, expected_values: Dict, on_failure, save_to_state, forwarder, state):
        self.expected_values = expected_values
        super().__init__(name, on_failure, save_to_state, forwarder, state)

    async def run(self, result: Result):
        """
        Run the check on the given reply.

        Parameters
        ----------
        reply : :ckl
            The reply to check: A tuple of (status code, result) per host.

        Return
        ------
        Tuple[bool, :class:`Result` or None]
            True if the check passed, otherwise False and the result of the on_failure action.
        """
        failed_hosts = set()

        reply = dict()
        for r in result.results.values():
            reply.update(r)

        for host, result_ in reply.items():
            if not result_:
                for name in self.expected_values.keys():
                    logger.debug(f"/{self._name}: Missing value '{name}' in reply from {host}.")
                    failed_hosts.add(host)
                    result.report_failure(self._name, host, "missing", name)
                continue
            for name, value in result_.items():
                if name not in self.expected_values:
                    logger.debug(f"Found additional value in reply from {host}/{self._name}.")
                    continue
                if value != self.expected_values[name]:
                    logger.debug(f"/{self._name}: Bad value '{name}' in reply from {host}.")
                    logger.debug(f"Expected {self.expected_values[name]} but found {value}.")
                    failed_hosts.add(host)
                    result.report_failure(self._name, host, "value", name)
            for name in self.expected_values.keys():
                if name not in result_.keys():
                    logger.debug(f"/{self._name}: Missing value '{name}' in reply from {host}.")
                    failed_hosts.add(host)
                    result.report_failure(self._name, host, "missing", name)
        if failed_hosts:
            logger.info(
                f"/{self._name}: Check reply for values failed: {[host.url() for host in failed_hosts]}"
            )
            result.embed(self._name, await self.on_failure(failed_hosts))
            return False
        self._save_reply(reply)
        return True


class TypeReplyCheck(ReplyCheck):
    """Check for the types of fields in the replies."""

    def __init__(self, name, expected_types: Dict, on_failure, save_to_state, forwarder, state):
        # Check configuration
        for valname, type_ in expected_types.items():
            if not locate(type_):
                raise RuntimeError(f"Value '{valname}' has unknown type '{type_}'.")
            expected_types[valname] = type_
        self._expected_types = expected_types
        super().__init__(name, on_failure, save_to_state, forwarder, state)

    async def run(self, result: Result):
        """
        Run the check on the given reply.

        Parameters
        ----------
        reply : :class:`Result`
            The reply to check in a result object.

        Return
        ------
        :class:`Result` or None
            None if the check passed, otherwise the result of the on_failure action.
        """
        failed_hosts = set()

        reply = dict()
        for r in result.results.values():
            if r:
                reply.update(r)

        for host, result_ in reply.items():
            if not result_:
                for name in self._expected_types.keys():
                    logger.debug(f"/{self._name}: Missing value '{name}' in reply from {host}.")
                    failed_hosts.add(host)
                    result.report_failure(self._name, host, "missing", name)
                continue
            for name, value in result_.items():
                if name not in self._expected_types:
                    logger.debug(f"Found additional value in reply from {host}/{self._name}.")
                    continue
                if not isinstance(value, locate(self._expected_types[name])):
                    logger.debug(
                        f"/{self._name}: Value '{name}' in reply from {host} is of type "
                        f"{type(value).__name__} (expected {self._expected_types[name]}"
                        f")."
                    )
                    failed_hosts.add(host)
                    result.report_failure(self._name, host, "type", name)
            for name in self._expected_types.keys():
                if name not in result_.keys():
                    logger.debug(f"/{self._name}: Missing value '{name}' in reply from {host}.")
                    failed_hosts.add(host)
                    result.report_failure(self._name, host, "missing", name)
        if failed_hosts:
            logger.info(
                f"/{self._name}: Check reply for value types failed: {[host.url() for host in failed_hosts]}"
            )
            result.embed(self._name, await self.on_failure(failed_hosts))
            return False
        self._save_reply(reply)
        return True
