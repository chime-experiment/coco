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
        self._result = dict()
        self._status = dict()
        self.add_result(name, result)
        self._error = error
        self._embedded = None
        self.type = type
        self._msg = None
        self._state = dict()
        self._embedded = dict()

    def add_result(self, name, result):
        """
        Add a result.

        Parameters
        ----------
        name : str
            Name of the result (e.g. endpoint name)
        result : dict
            Keys are host names (str) and values are str. Default `None`.
        """
        if result:
            if name not in self._result:
                self._result[name] = dict()
            if name not in self._status:
                self._status[name] = dict()
            res = dict()
            stat = dict()
            for h, r in result.items():
                res[h] = r[0]
                stat[h] = r[1]
            self._result[name].update(res)
            self._status[name].update(stat)

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
        d = dict()
        if self._embedded:
            for name, embedded_result in self._embedded.items():
                d[name] = embedded_result.report(type)

        if self._error:
            d[self._name] = dict()
            d[self._name]["error"] = self._error
            if self._msg:
                d[self._name]["message"] = self._msg
            return d

        if type == "OVERVIEW":
            if self._result:
                for name, result in self._result.items():
                    d[name] = dict()
                    for r in result.values():
                        try:
                            d[name][str(r)] += 1
                        except KeyError:
                            d[name][str(r)] = 1
            if self._msg:
                d["message"] = self._msg
            return d
        if type == "FULL":
            if self._result:
                for name, result in self._result.items():
                    d[name] = dict()
                    for h in result:
                        d[name][h] = dict()
                        d[name][h]["reply"] = result[h]
                        d[name][h]["status"] = self._status[name][h]
            if self._msg:
                d["message"] = self._msg
            return d
        if type == "CODES":
            d.update(self._status)
            if self._msg:
                d["message"] = self._msg
            return d
        if type == "CODES_OVERVIEW":
            if self._status:
                for name, status in self._status.items():
                    d[name] = dict()
                    for s in status.values():
                        try:
                            d[name][str(s)] += 1
                        except KeyError:
                            d[name][str(s)] = 1
            if self._msg:
                d["message"] = self._msg
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
            self._embedded[name] = Result(name, result, error)
        elif isinstance(result, Result):
            self._embedded[name] = result
        else:
            msg = f"Failure embedding results of /{name}."
            logger.error(msg)
            self._embedded[name] = Result(name, None, msg)
