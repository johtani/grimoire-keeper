"""Process-level exclusive lock for the dedicated job worker."""

import errno
import fcntl
import os
from pathlib import Path
from types import TracebackType


class WorkerAlreadyRunningError(RuntimeError):
    """Raised when another worker already owns the storage lock."""


class WorkerLock:
    """Hold an OS file lock for one SQLite-backed worker process."""

    def __init__(self, database_path: str):
        resolved_database = Path(database_path).resolve()
        self.path = Path(f"{resolved_database}.worker.lock")
        self._file_descriptor: int | None = None

    def acquire(self) -> None:
        """Acquire the lock without waiting for an existing worker."""
        if self._file_descriptor is not None:
            return

        file_descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(file_descriptor)
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise WorkerAlreadyRunningError(
                    "Another job worker is already using database "
                    f"{str(self.path).removesuffix('.worker.lock')}"
                ) from error
            raise
        self._file_descriptor = file_descriptor

    def release(self) -> None:
        """Release the lock if this instance owns it."""
        file_descriptor = self._file_descriptor
        if file_descriptor is None:
            return
        self._file_descriptor = None
        try:
            fcntl.flock(file_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(file_descriptor)

    def __enter__(self) -> "WorkerLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
