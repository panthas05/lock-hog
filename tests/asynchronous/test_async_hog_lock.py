import asyncio
import unittest

import lock_hog
from lock_hog.asynchronous.async_hog_lock import HoggerStillExecuting


class CouldNotAcquireLock(Exception):
    pass


class AsyncLockHogger(lock_hog.AsyncLockHogger):
    def __init__(
        self,
        *,
        lock: asyncio.Lock,
    ) -> None:
        self.lock = lock

    async def acquire_lock(self) -> None:
        await self.lock.acquire()

    async def release_lock(self) -> None:
        self.lock.release()


class SlowReleaseAsyncLockHogger(AsyncLockHogger):
    """
    The same as AsyncLockHogger, but waits for a second before releasing the lock. We
    do this only so that we can test the timeout handling.
    """

    async def release_lock(self) -> None:
        await asyncio.sleep(1.0)
        return await super().release_lock()


class TestAsyncHogLock(unittest.IsolatedAsyncioTestCase):
    async def test_acquires_lock_on_entry_and_releases_lock_on_exit(self) -> None:
        lock = asyncio.Lock()

        lock_hogger = AsyncLockHogger(lock=lock)

        # safety check
        self.assertFalse(
            lock.locked(),
            msg="Lock acquired before async_hog_lock context block was entered.",
        )

        async with lock_hog.async_hog_lock(lock_hogger=lock_hogger):
            self.assertTrue(
                lock.locked(),
                msg="Lock not acquired when within async_hog_lock context block.",
            )

        self.assertFalse(
            lock.locked(),
            msg="Lock not released after exiting async_hog_lock context block.",
        )

    async def test_raises_lock_hogging_task_is_still_executing_after_timeout(
        self,
    ) -> None:
        slow_release_lock_hogger = SlowReleaseAsyncLockHogger(lock=asyncio.Lock())

        passed_timeout = 0.01

        with self.assertRaisesRegex(
            HoggerStillExecuting,
            (
                "The task that hogged the lock was still executing after "
                f"{passed_timeout} seconds."
            ),
        ):
            async with lock_hog.async_hog_lock(
                lock_hogger=slow_release_lock_hogger,
                timeout=passed_timeout,
            ):
                pass

    async def test_hogger_still_alive_exception_message_with_one_second_timeout(
        self,
    ) -> None:
        slow_release_lock_hogger = SlowReleaseAsyncLockHogger(lock=asyncio.Lock())

        passed_timeout = 1.0

        with self.assertRaisesRegex(
            HoggerStillExecuting,
            "The task that hogged the lock was still executing after 1 second.",
        ):
            async with lock_hog.async_hog_lock(
                lock_hogger=slow_release_lock_hogger,
                timeout=passed_timeout,
            ):
                pass
