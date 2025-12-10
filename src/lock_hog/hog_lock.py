import contextlib
import enum
import multiprocessing
import threading
import typing
from multiprocessing.synchronize import Event as MultiprocessingEvent

Executor = threading.Thread | multiprocessing.Process
Event = threading.Event | MultiprocessingEvent


def _hog_lock_until_instructed_to_release(
    *,
    context_manager_that_acquires_lock: contextlib.AbstractContextManager[None],
    lock_acquired_event: Event,
    release_lock_event: Event,
) -> None:
    with context_manager_that_acquires_lock:
        lock_acquired_event.set()
        release_lock_event.wait()


class HogFrom(enum.StrEnum):
    THREAD = "THREAD"
    PROCESS = "PROCESS"


def _hog_lock(
    *,
    hog_from: HogFrom,
    context_manager_that_acquires_lock: contextlib.AbstractContextManager[None],
) -> tuple[Executor, Event]:
    if hog_from == HogFrom.THREAD:
        lock_acquired_event = threading.Event()
        release_lock_event = threading.Event()
        executor_class = threading.Thread
    elif hog_from == HogFrom.PROCESS:
        lock_acquired_event = multiprocessing.Event()
        release_lock_event = multiprocessing.Event()
        executor_class = multiprocessing.Process
    else:
        typing.assert_never(hog_from)

    executor = executor_class(
        target=_hog_lock_until_instructed_to_release,
        kwargs={
            "context_manager_that_acquires_lock": context_manager_that_acquires_lock,
            "lock_acquired_event": lock_acquired_event,
            "release_lock_event": release_lock_event,
        },
        # Don't prevent the programme from exiting - this is only a test utility
        daemon=True,
    )

    executor.start()
    # wait until the executor signals that it has acquired the lock
    lock_acquired_event.wait()

    return executor, release_lock_event


DEFAULT_JOIN_TIMEOUT = 1.0


class HoggerStillAlive(Exception):
    pass


@contextlib.contextmanager
def hog_lock(
    lock_hogger: contextlib.AbstractContextManager[None],
    *,
    hog_from: HogFrom = HogFrom.THREAD,
    timeout: float | None = None,
) -> typing.Generator[None, None, None]:
    hogger_executor, release_lock_event = _hog_lock(
        hog_from=hog_from,
        context_manager_that_acquires_lock=lock_hogger,
    )

    yield

    release_lock_event.set()

    timeout = timeout or DEFAULT_JOIN_TIMEOUT
    hogger_executor.join(timeout=timeout)
    if hogger_executor.is_alive():
        alive_time_description = "1 second" if timeout == 1.0 else f"{timeout} seconds"
        raise HoggerStillAlive(
            f"The {hog_from.value.lower()} that hogged the lock was still alive after "
            f"{alive_time_description}. If this doesn't indicate a bug, consider "
            "passing a longer timeout value to `hog_lock`."
        )
