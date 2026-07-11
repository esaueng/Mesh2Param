from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol


class _BinaryReader(Protocol):
    def read(self, size: int = -1) -> bytes: ...


class _BinaryWriter(Protocol):
    def write(self, data: bytes) -> int | None: ...


class ByteLimitExceeded(ValueError):
    """A bounded stream exceeded its configured byte cap."""

    code = "byte_limit_exceeded"

    def __init__(self, *, limit_bytes: int, observed_bytes: int) -> None:
        self.limit_bytes = limit_bytes
        self.observed_bytes = observed_bytes
        super().__init__(f"stream exceeds the {limit_bytes}-byte limit")

    def to_dict(self) -> dict[str, int | str]:
        return {
            "code": self.code,
            "limitBytes": self.limit_bytes,
            "observedBytes": self.observed_bytes,
        }


def _validate_limit(max_bytes: int, chunk_size: int | None = None) -> None:
    if isinstance(max_bytes, bool) or max_bytes < 0:
        raise ValueError("max_bytes must be a non-negative integer")
    if chunk_size is not None and (isinstance(chunk_size, bool) or chunk_size <= 0):
        raise ValueError("chunk_size must be a positive integer")


def iter_limited(chunks: Iterable[bytes], *, max_bytes: int) -> Iterator[bytes]:
    """Yield complete chunks while enforcing a cumulative cap before publication."""

    _validate_limit(max_bytes)
    observed = 0
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise TypeError("stream chunks must be bytes")
        if not chunk:
            continue
        observed += len(chunk)
        if observed > max_bytes:
            raise ByteLimitExceeded(limit_bytes=max_bytes, observed_bytes=observed)
        yield chunk


def write_chunks_limited(
    chunks: Iterable[bytes], destination: _BinaryWriter, *, max_bytes: int
) -> int:
    """Write byte chunks to a binary destination with a hard cumulative cap."""

    written = 0
    for chunk in iter_limited(chunks, max_bytes=max_bytes):
        result = destination.write(chunk)
        if result is not None and result != len(chunk):
            raise OSError("short write while copying bounded stream")
        written += len(chunk)
    return written


def copy_limited(
    source: _BinaryReader,
    destination: _BinaryWriter,
    *,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> int:
    """Copy from a file-like object without ever accepting more than ``max_bytes``."""

    _validate_limit(max_bytes, chunk_size)
    observed = 0
    while True:
        remaining = max_bytes - observed
        chunk = source.read(min(chunk_size, remaining + 1))
        if not isinstance(chunk, bytes):
            raise TypeError("binary stream read() must return bytes")
        if not chunk:
            return observed
        observed += len(chunk)
        if observed > max_bytes:
            raise ByteLimitExceeded(limit_bytes=max_bytes, observed_bytes=observed)
        result = destination.write(chunk)
        if result is not None and result != len(chunk):
            raise OSError("short write while copying bounded stream")


def read_limited(
    source: _BinaryReader, *, max_bytes: int, chunk_size: int = 1024 * 1024
) -> bytes:
    """Read a bounded binary stream into memory."""

    chunks: list[bytes] = []

    class _Collector:
        def write(self, chunk: bytes) -> int:
            chunks.append(chunk)
            return len(chunk)

    copy_limited(source, _Collector(), max_bytes=max_bytes, chunk_size=chunk_size)
    return b"".join(chunks)


def collect_limited(chunks: Iterable[bytes], *, max_bytes: int) -> bytes:
    """Accumulate request-body chunks under an explicit byte cap."""

    return b"".join(iter_limited(chunks, max_bytes=max_bytes))


__all__ = [
    "ByteLimitExceeded",
    "collect_limited",
    "copy_limited",
    "iter_limited",
    "read_limited",
    "write_chunks_limited",
]
