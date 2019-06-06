"""
coco endpoint queue.

This module receives endpoint calls for coco. coco serializes endpoint calls using redis.
"""
import asyncio


class Queue:

    async def worker(self, queue):
        print("Worker starting")
        while True:
            job = await queue.get()
            size = queue.qsize()
            print(f"Worker is sleeping on the job for {job}. {size} remaining")
            await asyncio.sleep(job)
            print("done working")

    async def add(self, queue, n):
        print(f"Adding {n} to queue. Now has size {queue.qsize()}")
        await queue.put(n)
