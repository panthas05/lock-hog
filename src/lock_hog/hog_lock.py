import contextlib
import threading
import typing


def _hog_lock_until_instructed_to_release(
    *,
    context_manager_that_acquires_lock: contextlib.AbstractContextManager[None],
    lock_acquired_event: threading.Event,
    release_lock_event: threading.Event,
) -> None:
    with context_manager_that_acquires_lock:
        lock_acquired_event.set()
        release_lock_event.wait()


def _hog_lock_from_thread(
    *,
    context_manager_that_acquires_lock: contextlib.AbstractContextManager[None],
) -> tuple[threading.Thread, threading.Event]:
    release_lock_event = threading.Event()

    lock_acquired_event = threading.Event()
    hogging_thread = threading.Thread(
        target=_hog_lock_until_instructed_to_release,
        kwargs={
            "context_manager_that_acquires_lock": context_manager_that_acquires_lock,
            "lock_acquired_event": lock_acquired_event,
            "release_lock_event": release_lock_event,
        },
        # Don't prevent the programme from exiting - this is only a test utility
        daemon=True,
    )

    hogging_thread.start()
    # wait until the hogging thread signals that it has acquired the lock
    lock_acquired_event.wait()

    return hogging_thread, release_lock_event


DEFAULT_THREAD_JOIN_TIMEOUT = 1.0


class HoggerStillAlive(Exception):
    pass


@contextlib.contextmanager
def hog_lock(
    lock_hogger: contextlib.AbstractContextManager[None],
    *,
    timeout: float | None = None,
) -> typing.Generator[None, None, None]:
    hogging_thread, release_lock_event = _hog_lock_from_thread(
        context_manager_that_acquires_lock=lock_hogger,
    )

    yield

    release_lock_event.set()

    timeout = timeout or DEFAULT_THREAD_JOIN_TIMEOUT
    hogging_thread.join(timeout=timeout)
    if hogging_thread.is_alive():
        alive_time_description = "1 second" if timeout == 1.0 else f"{timeout} seconds"
        raise HoggerStillAlive(
            f"The thread that hogged the lock was still alive after "
            f"{alive_time_description}. If this doesn't indicate a bug, consider "
            "passing a longer timeout value to `hog_lock`."
        )
