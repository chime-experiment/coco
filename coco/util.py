"""
Utility functions.

The str2time* functions were stolen from dias
(https://github.com/chime-experiment/dias/blob/master/dias/utils/string_converter.py).
"""

import re
from datetime import timedelta

TIMEDELTA_REGEX = re.compile(r"((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?")


def str2timedelta(time_str):
    """
    Convert a string to a timedelta.
    Parameters
    ----------
    time_str : str
        A string representing a timedelta in the form `<int>h`, `<int>m`,
        `<int>s` or a combination of the three.
    Returns
    -------
    :class:`datetime.timedelta`
        The converted timedelta.
    """
    # Check for simple numeric seconds
    try:
        seconds = int(time_str)
        return timedelta(seconds=seconds)
    except ValueError:
        pass

    # Otherwise parse time
    parts = TIMEDELTA_REGEX.match(time_str)
    if not parts:
        return
    parts = parts.groupdict()
    time_params = {}
    for (name, param) in parts.items():
        if param:
            time_params[name] = int(param)
    return timedelta(**time_params)


def str2total_seconds(time_str):
    """
    Convert that describes a timedelta directly to seconds.
    Parameters
    ----------
    time_str : str
        A string representing a timedelta in the form `<int>h`, `<int>m`,
        `<int>s` or a combination of the three.
    Returns
    -------
    float
        Timedelta in seconds.
    """
    return str2timedelta(time_str).total_seconds()
