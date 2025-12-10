import multiprocessing
import threading
import time
import unittest
from multiprocessing.synchronize import Lock as MultiprocessingLock

import lock_hog
from lock_hog.parallel.hog_lock import HoggerStillAlive


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


class TestHogLockFromThread(unittest.TestCase):
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


class ProcessLockHogger(lock_hog.LockHogger):
    def __init__(
        self,
        *,
        lock: MultiprocessingLock,
    ) -> None:
        self.lock = lock

    def acquire_lock(self) -> None:
        lock_acquired = self.lock.acquire(block=False)
        if not lock_acquired:
            raise CouldNotAcquireLock()

    def release_lock(self) -> None:
        self.lock.release()


class SlowReleaseProcessLockHogger(ProcessLockHogger):
    """
    The same as ProcessLockHogger, but waits for one and a half seconds before releasing
    the lock. We do this so that we can test timeout handling.
    """

    def release_lock(self) -> None:
        time.sleep(1.5)
        return super().release_lock()


class TestHogLockFromProcess(unittest.TestCase):
    def setUp(self) -> None:
        self.lock = multiprocessing.Lock()
        return super().setUp()

    def _lock_is_locked(self) -> bool:
        """
        If we managed to acquire the lock, it wasn't locked/acquired by another
        process, so we use that value to determine the return value of this function.
        However, we don't want to pollute test state, so if we did manage to acquire the
        lock, release it so it goes back into its unlocked/unacquired state
        """
        # TODO: replace this method with calls to lock.locked() when python 3.14 becomes
        # the minimum supported version.
        acquired_lock = self.lock.acquire(block=False)
        if acquired_lock:
            self.lock.release()
        return not acquired_lock

    def test_acquires_lock_on_entry_and_releases_lock_on_exit(self) -> None:
        lock_hogger = ProcessLockHogger(lock=self.lock)

        # safety check
        self.assertFalse(
            self._lock_is_locked(),
            msg="Lock acquired before hog_lock context block was entered.",
        )

        with lock_hog.hog_lock(
            lock_hogger=lock_hogger,
            hog_from=lock_hog.HogFrom.PROCESS,
        ):
            self.assertTrue(
                self._lock_is_locked(),
                msg="Lock not acquired when within hog_lock context block.",
            )

        self.assertFalse(
            self._lock_is_locked(),
            msg="Lock not released after exiting hog_lock context block.",
        )

    def test_raises_lock_hogging_process_is_still_alive_after_timeout(self) -> None:
        slow_release_lock_hogger = SlowReleaseProcessLockHogger(lock=self.lock)

        passed_timeout = 0.01

        with self.assertRaisesRegex(
            HoggerStillAlive,
            (
                "The process that hogged the lock was still alive after "
                f"{passed_timeout} seconds."
            ),
        ):
            with lock_hog.hog_lock(
                lock_hogger=slow_release_lock_hogger,
                hog_from=lock_hog.HogFrom.PROCESS,
                timeout=passed_timeout,
            ):
                pass

    def test_hogger_still_alive_exception_message_with_one_second_timeout(self) -> None:
        slow_release_lock_hogger = SlowReleaseProcessLockHogger(lock=self.lock)

        with self.assertRaisesRegex(
            HoggerStillAlive,
            "The process that hogged the lock was still alive after 1 second.",
        ):
            with lock_hog.hog_lock(
                lock_hogger=slow_release_lock_hogger,
                hog_from=lock_hog.HogFrom.PROCESS,
                timeout=1.0,
            ):
                pass
