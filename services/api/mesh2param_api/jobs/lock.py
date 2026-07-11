from __future__ import annotations

import os
import stat
from contextlib import suppress
from pathlib import Path
from typing import IO


class WorkerAlreadyRunningError(RuntimeError):
    """The shared SQLite data directory already has a queue supervisor."""


class WorkerInstanceLock:
    """Advisory singleton lock held for the lifetime of a SQLite queue supervisor."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._stream: IO[bytes] | None = None

    def __enter__(self) -> WorkerInstanceLock:
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except OSError as exc:
            raise WorkerAlreadyRunningError(
                f"cannot safely open the geometry worker lock: {self.path}"
            ) from exc
        stream = os.fdopen(descriptor, "r+b", closefd=True)
        try:
            status = os.fstat(stream.fileno())
            if not stat.S_ISREG(status.st_mode):
                raise WorkerAlreadyRunningError("geometry worker lock is not a regular file")
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise WorkerAlreadyRunningError(
                    "another geometry worker already owns this SQLite data directory"
                ) from exc
            stream.seek(0)
            stream.truncate()
            stream.write(f"{os.getpid()}\n".encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
        except Exception:
            stream.close()
            raise
        self._stream = stream
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self._stream is None:
            return
        import fcntl

        with suppress(OSError):
            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        self._stream.close()
        self._stream = None


__all__ = ["WorkerAlreadyRunningError", "WorkerInstanceLock"]
