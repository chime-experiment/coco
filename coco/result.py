"""coco endpoint call result."""
import logging
from typing import Tuple, Dict

TYPES = ["OVERVIEW", "FULL", "CODES", "CODES_OVERVIEW"]

logger = logging.getLogger(__name__)


class Result:
    """
    Result of a coco endpoint call.

    Description of the available report types:
    - OVERVIEW:
        `{
        5: "Error message",
        134: "Success"
        }`
    - FULL:
        `{
        "host1": "Error message",
        "host2": "Success",
        "host3": {"status": "OK", "result": 1}
        }`
    - CODES:
        `{
        "host1": "200",
        "host2": "0",
        "host3": "404
        }`
    - CODES_OVERVIEW:
        `{
        5: "404",
        23: "200"
        }`

    A status code of 0 signals an internal or connection error.
    """

    def __init__(self, name, result=None, error=None, type="CODES_OVERVIEW"):
        """
        Construct a Result.

        Parameters
        ----------
        name : str
            Name of the result (e.g. endpoint name)
        result : dict
            Keys are host names (str) and values are str. Default `None`.
        error : str
            If an error is set, the result will be ignored in any report and only the error
            message is returned. Default `None`
        type : str
            Type of report to use. See :class:`Result` for a full description. Default
            `CODES_OVERVIEW`.
        """
        self._name = name
        self._result = dict()
        self._status = dict()
        self._add_reply(name, result)
        self._error = error
        self._embedded = None
        self.type = type
        self._msg = None
        self._state = dict()
        self._embedded = dict()
        self._checks = dict()
        self._success = True

    @property
    def name(self) -> str:
        """
        Get name of the endpoint this result is for.

        Returns
        -------
        str
            Name.
        """
        return self._name

    @property
    def success(self) -> bool:
        """
        Get result success.

        Returns
        -------
        bool
            True if successful, otherwise False.
        """
        return self._success

    @success.setter
    def success(self, value):
        """
        Set the result success.

        Parameters
        ----------
        value : bool
            True if successful, otherwise False.
        """
        self._success = value

    def result(self, name: str) -> Dict:
        """
        Get replies saved in this result.

        Parameters
        ----------
        name : str
            Name of the result to get.

        Returns
        -------
        dict
            Replies in a dict with hosts as keys.
        """
        return self._result[name]

    @property
    def results(self) -> Dict:
        """
        Get all replies saved in this result.

        Returns
        -------
        dict
            Replies in a dict with endpoint names as keys.
        """
        return self._result

    def report_failure(self, forward_name, host, failure_type, varname):
        """
        Report a failure when checking the reply from forwarding an endpoint call to a host.

        Parameters
        ----------
        forward_name : str
            The name of the forward endpoint.
        host : :class:`Host`
            The host that send a bad reply.
        failure_type : str
            Currently either "missing" or "type".
        varname : str
            The name of the reply field that was bad.
        """
        this_check = (
            self._checks.setdefault(forward_name, dict())
            .setdefault(host.url(), dict())
            .setdefault("reply", dict())
            .setdefault(failure_type, list())
        )
        this_check.append(varname)

    def add_result(self, result):
        """
        Add a result to this result object.

        Parameters
        ----------
        result : :class:`Result`
            Result to add.
        """
        if not result:
            return
        self._success &= result.success
        self._result.update(result._result)
        self._status.update(result._status)
        self._checks.update(result._checks)
        self._state.update(result._state)
        self._embedded.update(result._embedded)
        if self._error:
            if result._error:
                self._error = self._error + " ;" + result._error
        else:
            self._error = result._error
        if self._msg:
            self._msg.append(result._msg)
        else:
            self._msg = result._msg

    def _add_reply(self, name: str, result: Dict[str, Tuple[str, int]]):
        """
        Add a reply to this result object.

        Parameters
        ----------
        name : str
            Name of the result.
        result : dict
            Keys are host names (str) and values (result, HTTP status code).
        """
        if result:
            self._result[name] = dict()
            self._status[name] = dict()
            for h, r in result.items():
                self._result[name][h] = r[0]
                self._status[name][h] = r[1]
        else:
            self._result[name] = None
            self._status[name] = None

    def add_message(self, msg):
        """
        Add a message to the result.

        Parameters
        ----------
        msg : str
            Message

        Returns
        -------
        :class:`Result`
            The Result object containing the message.
        """
        if self._msg is None:
            self._msg = msg
        elif isinstance(self._msg, list):
            self._msg.append(msg)
        else:
            self._msg = [self._msg, msg]
        return self

    def state(self, state):
        """
        Add a state to the result.

        Parameters
        ----------
        state : dict
            The state.
        """
        self._state.update(state)

    def report(self, report_type=None):
        """
        Generate a report.

        Parameters
        ----------
        report_type : str
            Type of report to use. See :class:`Result` for a full description.

            If report_type is `None`, the type previously stored in the `Result` object is used
            (default: `"CODES_OVERVIEW").

        Returns
        -------
        dict
            Reports of this and any embedded results. Keys are the result names and values
            are dictionaries with a format according to the report type.
            If available, a message is attached with the key `"message"`.
        """
        if report_type is None:
            report_type = self.type
        d = dict()
        if self._embedded:
            for name, embedded_result in self._embedded.items():
                d[name] = embedded_result.report(report_type)

        if self._msg:
            d["message"] = self._msg

        d["success"] = self._success

        if self._error:
            d["error"] = self._error
            return d

        if self._state:
            d["state"] = self._state

        if self._checks:
            d["failed_checks"] = self.report_checks(report_type)

        if report_type == "OVERVIEW":
            for name in self._result.keys():
                if self._result[name]:
                    d[name] = dict()
                    for r in self._result[name].values():
                        try:
                            d[name][str(r)] += 1
                        except KeyError:
                            d[name][str(r)] = 1
            return d
        if report_type == "FULL":
            for name in self._result.keys():
                if self._result[name]:
                    d[name] = dict()
                    for h in self._result[name].keys():
                        d[name][h.url()] = dict()
                        d[name][h.url()]["reply"] = self._result[name][h]
                        d[name][h.url()]["status"] = self._status[name][h]
            return d
        if report_type == "CODES":
            d.update(self._status)
            return d
        if report_type == "CODES_OVERVIEW":
            for name in self._result.keys():
                if self._status[name]:
                    d[name] = dict()
                    for s in self._status[name].values():
                        try:
                            d[name][str(s)] += 1
                        except KeyError:
                            d[name][str(s)] = 1
            return d
        else:
            msg = f"Unknown report type: {report_type}"
            logger.error(msg)
            d["error"] = msg
            return d

    def report_checks(self, report_type):
        """
        Build a dict that reports the failed checks according to the report type.

        Parameters
        ----------
        report_type : str
            Report type to use.

        Returns
        -------
        dict
            Report of failed checks.
        """
        # _checks looks like this:
        # endpoint name:
        #   host:
        #       reply:
        #           missing/type: [varname]

        if report_type == "OVERVIEW" or report_type == "CODES_OVERVIEW":
            # count number of host with same failures
            report = dict()
            for endpoint, e_checks in self._checks.items():
                report[endpoint] = dict()
                report[endpoint]["reply"] = dict()
                for host, h_checks in e_checks.items():
                    for failure, varlist in h_checks["reply"].items():
                        report[endpoint]["reply"][failure] = dict()
                        varlist = "[" + ", ".join(varlist) + "]"
                        try:
                            report[endpoint]["reply"][failure][varlist] += 1
                        except KeyError:
                            report[endpoint]["reply"][failure][varlist] = 1
            return report
        if report_type == "FULL" or report_type == "CODES":
            return self._checks
        else:
            report = dict()
            msg = f"Unknown report type: {report_type}"
            logger.error(msg)
            report["error"] = msg
            return report

    def embed(self, name, result, error=None):
        """
        Embed the result of another endpoint call inside this result.

        Will be kept as an embedded result inside this result, but for reports the hierarchy gets
        flattened.

        Parameters
        ----------
        name : str
            Name of the result (e.g. endpoint name).
        result : dict or :class:`Result`
            If this is a dictionary: Keys are host names, values are str.
        error : str
            If an error is set, the result will be ignored in any report and only the error
            message is returned.
        """
        if result is None:
            self._embedded[name] = Result(name, None)
        elif isinstance(result, dict):
            self._embedded[name] = Result(name, result, error)
        elif isinstance(result, Result):
            self._success &= result.success
            self._embedded[name] = result
        else:
            msg = f"Failure embedding results of /{name}."
            logger.error(msg)
            self._embedded[name] = Result(name, None, msg)
