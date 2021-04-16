"""
Coco task pool.

Adapted from https://gist.github.com/cgarciae/6d069a000cdd79f50c746199fa9597b2#file-task_pool-py
"""
import asyncio


class TaskPool:
    """Pool async tasks and run them concurrently up to a given limit."""

    def __init__(self, workers):
        self._semaphore = asyncio.Semaphore(workers)
        self._tasks = set()

    async def put(self, coro):
        """
        Put a task.

        Parameters
        ----------
        coro : Coroutine to add task for.
        """
        await self._semaphore.acquire()

        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)

    def _on_task_done(self, _):
        self._semaphore.release()

    async def join(self):
        """
        Gather all tasks and return their results.

        Returns
        -------
        list
            Results of all tasks.
        """
        results = await asyncio.gather(*self._tasks, return_exceptions=False)
        self._tasks = set()
        return results

    async def __aenter__(self):
        """Context manager for entering `async with`."""
        return self

    def __aexit__(self, exc_type, exc, tb):
        """Context manager for exiting `async with`."""
        return self.join()
