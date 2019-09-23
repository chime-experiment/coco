"""
coco slack logging module.

Exports messages to slack.

Modified from <https://github.com/imbolc/aiolog> and
<https://github.com/founders4schools/python-webhook-logger>
"""

# Copyright (c) 2011 Imbolc.
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.


import logging
import asyncio
import aiohttp


class LogMessageQueue:
    """An async queue for processing log messages.

    Parameters
    ----------
    queue_size : int
        Maximum queue length.
    timeout : int
        Timeout for HTTP requests in seconds.
    """

    def __init__(self, queue_size=1000, timeout=60):
        self.queue = None
        self.queue_size = queue_size
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.started = False

    def start(self, loop):
        """Start up the loop processing messages.

        Parameters
        ----------
        loop : asyncio.loop
            The event loop to use.
        """
        self.loop = loop
        self.queue = asyncio.Queue(maxsize=self.queue_size, loop=loop)
        self.task = asyncio.ensure_future(self.consume(), loop=loop)
        self.started = True
        self.STOP_SIGNAL = object()

    def push(self, payload):
        """Place an item into the queue.

        Parameters
        ----------
        payload : dict
            Data to push.
        """
        if self.started:
            self.queue.put_nowait(payload)

    async def stop(self, timeout=60):
        """Stop the queue processing.

        Parameters
        ----------
        timeout : int
            Seconds to wait before just cancelling queued messages.
        """

        # Signal that we shouldn't add anything else into the queue
        self.started = False

        # Try to gracefully cleanup the items currently in the queue
        try:
            await asyncio.wait_for(self.queue.put(self.STOP_SIGNAL), timeout=timeout)
            await asyncio.wait_for(self.queue.join(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

        self.task.cancel()

    async def consume(self):
        """Process the queue of messages."""

        while True:
            entry = await self.queue.get()
            self.queue.task_done()

            # Exit if requested
            if entry is self.STOP_SIGNAL:
                break

            # Process the item
            await self.process_item(entry)

    async def process_item(self, entry):
        """Process a queue item.

        Parameters
        ----------
        entry : tuple
            URL, payload tuple.
        """
        pass


class TestQueue(LogMessageQueue):
    """Simple test queue that prints what gets pushed to it."""

    async def process_item(self, entry):
        """Print items to stdout."""
        print(entry)


class SlackMessageQueue(LogMessageQueue):
    """Post a pushed item to slack.

    Uses asyncio/aiohttp to push the message.
    """

    def __init__(self, *args, token=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = token

    async def process_item(self, data):
        """Process a queue item.

        Parameters
        ----------
        entry : tuple
            URL, payload tuple.
        """
        url = "https://slack.com/api/chat.postMessage"

        # Send the authorization token in the headers
        headers = {"Authorization": f"Bearer {self.token}"}

        async with aiohttp.ClientSession(loop=self.loop) as session:
            try:
                async with session.post(
                    url, json=data, headers=headers, timeout=self.timeout
                ) as response:
                    if response.status != 200:
                        print(
                            "Sending message to slack server failed with status: {} ({}).\nThis was the message:\n\t{}".format(
                                response.reason, response.status, data
                            )
                        )
            except Exception as e:
                print(
                    "Sending message to slack server failed: {}\nThis was the message:\n\t{}".format(
                        e, data
                    )
                )


# MIT License
#
# Copyright (c) 2017, Founders4Schools
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


class SlackLogHandler(logging.Handler):
    """Logging handler to post to Slack."""

    def __init__(self, channel, queue=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.channel = channel

        # Use the global SlackMessageQueue if not overidden
        self.queue = _slack_queue if queue is None else queue

        self.formatter = SlackLogFormatter()

    def emit(self, record):
        """Queue the log message to be sent to slack."""
        try:
            payload = self.format(record)
            payload["channel"] = self.channel
            self.queue.push(payload)
        except Exception:
            self.handleError(record)


class SlackLogFilter(logging.Filter):
    """Filter to allow slack messaging only when requested.

    Uses the `extra` kwargs to do this:

    >>> logger.info("My slack message", extra={'notify_slack': True})
    """

    def filter(self, record):
        """Filter a slack log message."""
        return getattr(record, "notify_slack", False)


class SlackLogFormatter(logging.Formatter):
    """Format a log message for slack.

    This converts the `LogRecord` into the dict representation that is
    specific to Slack's message format. Because of that, this class or a
    similar variant *must* be used with `SlackLogHandler`.
    """

    def __init__(self, title=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title

    def format(self, record):
        """Format the slack message content.

        This adds a timestamp for when it was logged and a coloured border
        depending on the severity of the message
        """
        ret = {
            "ts": record.created,
            "text": record.getMessage(),
            "title": record.name if self.title is None else self.title,
        }
        try:
            loglevel_colour = {
                "INFO": "good",
                "WARNING": "warning",
                "ERROR": "#E91E63",
                "CRITICAL": "danger",
            }
            ret["color"] = loglevel_colour[record.levelname]
        except KeyError:
            pass
        return {"attachments": [ret]}


# Module level slack message queue
_slack_queue = SlackMessageQueue()

# Add start/stop methods to be at the module level
start = _slack_queue.start
stop = _slack_queue.stop


def set_token(token):
    """Set the access token of the default Slack queue.

    Parameters
    ----------
    token : str
        Slack bot authorization token.
    """
    _slack_queue.token = token
