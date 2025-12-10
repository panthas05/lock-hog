import abc
import types


class LockHogger(abc.ABC):
    @abc.abstractmethod
    def acquire_lock(self) -> None: ...

    @abc.abstractmethod
    def release_lock(self) -> None: ...

    def __enter__(self) -> None:
        self.acquire_lock()

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception_value: BaseException | None,
        exception_traceback: types.TracebackType | None,
    ) -> None:
        self.release_lock()
