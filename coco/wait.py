"""Internal endpoint for coco that waits for a given time."""
import asyncio

from .exceptions import InvalidUsage
from .util import str2total_seconds


async def process_post(request: dict):
    """
    Process the POST request.

    Parameters
    ----------
    request : dict
        Needs to contain `duration : str`. TODO: add this to config checks on start-up when
        another endpoint forwards here.
        The duration string represents a timedelta in the form `<int>h`, `<int>m`,
        `<int>s` or a combination of the three.
    """
    if "duration" not in request:
        raise InvalidUsage("Value 'duration' not found in request.")
    try:
        duration = str2total_seconds(request["duration"])
    except Exception:
        raise InvalidUsage(
            f"Failed parsing value 'duration' ({duration})."
        ) from Exception

    await asyncio.sleep(duration)
