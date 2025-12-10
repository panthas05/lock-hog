import threading
import time
import unittest

import lock_hog
from lock_hog.hog_lock import HoggerStillAlive


class CouldNotAcquireLock(Exception):
    pass


class ThreadLockHogger(lock_hog.LockHogger):
    def __init__(
        self,
        *,
        lock: threading.Lock,
    ) -> None:
        self.lock = lock

    def acquire_lock(self) -> None:
        acquired_lock = self.lock.acquire(blocking=False)
        if not acquired_lock:
            raise CouldNotAcquireLock

    def release_lock(self) -> None:
        self.lock.release()


class SlowReleaseThreadLockHogger(ThreadLockHogger):
    """
    The same as ThreadLockHogger, but waits for one and a half seconds before releasing
    the lock. We do this so that we can test timeout handling.
    """

    def release_lock(self) -> None:
        time.sleep(1.5)
        return super().release_lock()


class TestHogLock(unittest.TestCase):
    def test_acquires_lock_on_entry_and_releases_lock_on_exit(self) -> None:
        lock = threading.Lock()

        lock_hogger = ThreadLockHogger(lock=lock)

        # safety check
        self.assertFalse(
            lock.locked(),
            msg="Lock acquired before hog_lock context block was entered.",
        )

        with lock_hog.hog_lock(lock_hogger=lock_hogger):
            self.assertTrue(
                lock.locked(),
                msg="Lock not acquired when within hog_lock context block.",
            )

        self.assertFalse(
            lock.locked(),
            msg="Lock not released after exiting hog_lock context block.",
        )

    def test_raises_lock_hogging_thread_is_still_alive_after_timeout(self) -> None:
        slow_release_lock_hogger = SlowReleaseThreadLockHogger(lock=threading.Lock())

        passed_timeout = 0.01

        with self.assertRaisesRegex(
            HoggerStillAlive,
            (
                "The thread that hogged the lock was still alive after "
                f"{passed_timeout} seconds."
            ),
        ):
            with lock_hog.hog_lock(
                lock_hogger=slow_release_lock_hogger,
                timeout=passed_timeout,
            ):
                pass

    def test_hogger_still_alive_exception_message_with_one_second_timeout(self) -> None:
        slow_release_lock_hogger = SlowReleaseThreadLockHogger(lock=threading.Lock())

        with self.assertRaisesRegex(
            HoggerStillAlive,
            "The thread that hogged the lock was still alive after 1 second.",
        ):
            with lock_hog.hog_lock(
                lock_hogger=slow_release_lock_hogger,
                timeout=1.0,
            ):
                pass
