"""coco endpoint call result."""
import logging
from collections import Counter, defaultdict

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

    def __init__(self, name, result, error=None, type="CODES_OVERVIEW"):
        """
        Construct a Result.

        Parameters
        ----------
        name : str
            Name of the result (e.g. endpoint name)
        result : dict
            Keys are host names (str) and values are str.
        error : str
            If an error is set, the result will be ignored in any report and only the error
            message is returned.
        type : str
            Type of report to use. See :class:`Result` for a full description.
        """
        self._name = name
        self._result = dict()
        self._status = dict()
        if result is None:
            self._result = None
            self._status = None
        else:
            for h, r in result.items():
                self._result[h] = r[0]
                self._status[h] = r[1]
        self._error = error
        self._embedded = None
        self.type = type
        self._msg = None

    def add(self, msg):
        """
        Add a message to the result.

        Parameters
        ----------
        msg : str
            Message
        """
        self._msg = msg

    def report(self, type=None):
        """
        Generate a report.

        Parameters
        ----------
        type : str
            Type of report to use. See :class:`Result` for a full description.

            If type is `None`, the type previously stored in the `Result` object is used
            (default: `"CODES_OVERVIEW").

        Returns
        -------
        dict
            Reports of this and any embedded results. Keys are the result names and values
            are dictionaries with a format according to the report type.
            If available, a message is attached with the key `"message"`.
        """
        if type is None:
            type = self.type
        if self._embedded is None:
            d = dict()
        else:
            d = self._embedded.report(type)

        if self._error:
            d[self._name] = dict()
            d[self._name]["error"] = self._error
            if self._msg:
                d[self._name]["message"] = self._msg
            return d

        if type == "OVERVIEW":
            res = dict()
            for r in self._result.values():
                try:
                    res[r] += 1
                except KeyError:
                    res[r] = 1
            d[self._name] = res
            if self._msg:
                d[self._name]["message"] = self._msg
            return d
        if type == "FULL":
            d[self._name] = dict()
            for h in self._result.keys():
                d[self._name][h] = dict()
                d[self._name][h]["result"] = self._result[h]
                d[self._name][h]["status"] = self._status[h]
            if self._msg:
                d[self._name]["message"] = self._msg
            return d
        if type == "CODES":
            d[self._name] = self._status
            if self._msg:
                d[self._name]["message"] = self._msg
            return d
        if type == "CODES_OVERVIEW":
            res = dict()
            for r in self._status.values():
                try:
                    res[str(r)] += 1
                except KeyError:
                    res[str(r)] = 1
            d[self._name] = res
            if self._msg:
                d[self._name]["message"] = self._msg
            return d
        else:
            msg = f"Unknown report type: {type}"
            logger.error(msg)
            return msg

    def embed(self, name, result, error=None):
        """
        Embed the result of another endpoint call inside this result.

        Parameters
        ----------
        name : str
            Name of the result (e.g. endpoint name).
        result : dict
            Keys are host names, values are str.
        error : str
            If an error is set, the result will be ignored in any report and only the error
            message is returned.
        """
        if isinstance(result, dict):
            self._embedded = Result(name, result, error)
        elif isinstance(result, Result):
            self._embedded = result
        else:
            msg = f"Failure embedding results of /{name}."
            logger.error(msg)
            self._embedded = Result(name, None, msg)
