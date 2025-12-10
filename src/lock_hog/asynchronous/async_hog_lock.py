import asyncio
import contextlib
import typing


async def _hog_lock_until_instructed_to_release(
    *,
    context_manager_that_acquires_lock: contextlib.AbstractAsyncContextManager[None],
    lock_acquired_event: asyncio.Event,
    release_lock_event: asyncio.Event,
) -> None:
    async with context_manager_that_acquires_lock:
        lock_acquired_event.set()
        await release_lock_event.wait()


class NoRunningEventLoop(Exception):
    pass


async def _hog_lock(
    *,
    context_manager_that_acquires_lock: contextlib.AbstractAsyncContextManager[None],
) -> tuple[asyncio.Task, asyncio.Event]:
    lock_acquired_event = asyncio.Event()
    release_lock_event = asyncio.Event()

    try:
        event_loop = asyncio.get_running_loop()
    except RuntimeError:
        raise NoRunningEventLoop(
            "Please ensure that `async_hog_lock` is called from within an async task, "
            "so that it has access to a running event loop."
        )

    task = event_loop.create_task(
        coro=_hog_lock_until_instructed_to_release(
            context_manager_that_acquires_lock=context_manager_that_acquires_lock,
            lock_acquired_event=lock_acquired_event,
            release_lock_event=release_lock_event,
        ),
        name=f"Async hog lock: {repr(context_manager_that_acquires_lock)}",
    )

    # wait until the task signals that it has acquired the lock
    await lock_acquired_event.wait()

    return task, release_lock_event


DEFAULT_TIMEOUT = 1.0


class HoggerStillAlive(Exception):
    pass


@contextlib.asynccontextmanager
async def async_hog_lock(
    lock_hogger: contextlib.AbstractAsyncContextManager[None],
    *,
    timeout: float | None = None,
) -> typing.AsyncIterator[None]:
    hogging_task, release_lock_event = await _hog_lock(
        context_manager_that_acquires_lock=lock_hogger,
    )

    yield

    release_lock_event.set()

    timeout = timeout or DEFAULT_TIMEOUT

    try:
        async with asyncio.timeout(timeout):
            await hogging_task
    except asyncio.TimeoutError:
        alive_time_description = "1 second" if timeout == 1.0 else f"{timeout} seconds"
        raise HoggerStillAlive(
            f"The task that hogged the lock was still executing after "
            f"{alive_time_description}. If this doesn't indicate a bug, consider "
            "passing a longer timeout value to `async_hog_lock`."
        )
