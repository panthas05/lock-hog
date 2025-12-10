import abc
import types


class AsyncLockHogger(abc.ABC):
    @abc.abstractmethod
    async def acquire_lock(self) -> None: ...

    @abc.abstractmethod
    async def release_lock(self) -> None: ...

    async def __aenter__(self) -> None:
        await self.acquire_lock()

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception_value: BaseException | None,
        exception_traceback: types.TracebackType | None,
    ) -> None:
        await self.release_lock()
