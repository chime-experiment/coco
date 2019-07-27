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


class HTTPPostQueue:
    """An async queue for sending HTTP Post requests.

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
        self.timeout = timeout
        self.started = False

    def start(self, loop):
        """Start up the loop processing PUSH messages.

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

    def push(self, url, payload):
        """Place an item into the PUSH queue.

        Parameters
        ----------
        url : string
            URL to push to.
        payload : dict
            Data to push.
        """
        if self.started:
            self.queue.put_nowait((url, payload))

    async def stop(self, timeout=60):
        """Stop the queue processing.

        Parameters
        ----------
        timeout : int
            Seconds to wait before just cancelling queued messages.
        """
        with asyncio.suppress(asyncio.TimeoutError):
            with asyncio.timeout_manager(timeout, loop=self.loop):
                await self.queue.put(self.STOP_SIGNAL)
                await self.queue.join()
                while self.started:
                    await asyncio.sleep(0.1, loop=self.loop)
        self.task.cancel()

    async def consume(self):
        """Process the queue of messages."""
        time_to_stop = False
        while not time_to_stop:
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

        url, data = entry

        async with aiohttp.ClientSession(loop=self.loop) as session:
            async with session.post(url, json=data) as response:
                if response.status != 200:
                    # TODO: log to a real logger at this point
                    pass


class TestQueue(HTTPPostQueue):
    """Simple test queue that prints what gets pushed to it."""
    async def process_item(self, entry):
        print(entry)


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

    # NOTE: Class level queue for posting, be careful about changing this. You
    # probably want to make sure you do this at class level
    #queue = TestQueue()
    queue = HTTPPostQueue()

    def __init__(self, hook_url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hook_url = hook_url
        self.formatter = SlackLogFormatter()

    def emit(self, record):
        """
        Submit the record with a POST request
        """
        try:
            payload = self.format(record)
            self.queue.push(self.hook_url, payload)
        except Exception:
            self.handleError(record)

    def filter(self, record):
        """
        Disable the logger if hook_url isn't defined,
        we don't want to do it in all environments (e.g local/CI)
        """
        if not self.hook_url:
            return 0
        return super().filter(record)


class SlackLogFilter(logging.Filter):
    """
    Logging filter to decide when logging to Slack is requested, using
    the `extra` kwargs:
        `logger.info("...", extra={'notify_slack': True})`
    """

    def filter(self, record):
        return getattr(record, 'notify_slack', False)


class SlackLogFormatter(logging.Formatter):

    def __init__(self, title=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title

    def format(self, record):
        """
        Format message content, timestamp when it was logged and a
        coloured border depending on the severity of the message
        """
        ret = {
            'ts': record.created,
            'text': record.getMessage(),
            'title': record.name if self.title is None else self.title
        }
        try:
            loglevel_colour = {
                'INFO': 'good',
                'WARNING': 'warning',
                'ERROR': '#E91E63',
                'CRITICAL': 'danger',
            }
            ret['color'] = loglevel_colour[record.levelname]
        except KeyError:
            pass
        return {'attachments': [ret]}
