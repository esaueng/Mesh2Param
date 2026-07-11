from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast

from .streams import ByteLimitExceeded, read_limited


class StorageError(RuntimeError):
    """Base error for content-addressed storage failures."""


class StorageIntegrityError(StorageError):
    """Stored content does not match its immutable content address."""


class UnsafeStoragePathError(StorageError):
    """A storage path is a symlink or a non-regular filesystem object."""


@dataclass(frozen=True, slots=True)
class StoredBlob:
    sha256: str
    byte_size: int
    path: Path
    deduplicated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "byteSize": self.byte_size,
            "path": str(self.path),
            "deduplicated": self.deduplicated,
        }


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY_FLAGS = _READ_FLAGS | getattr(os, "O_DIRECTORY", 0)
_CREATE_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


def _normalize_digest(digest: str) -> str:
    if not isinstance(digest, str):
        raise ValueError("SHA-256 digest must be a string")
    normalized = digest.casefold()
    if not _SHA256.fullmatch(normalized):
        raise ValueError("SHA-256 digest must contain exactly 64 hexadecimal characters")
    return normalized


def _ensure_directory(path: Path, *, mode: int = 0o700) -> None:
    with suppress(FileExistsError):
        path.mkdir(mode=mode, parents=True, exist_ok=False)
    try:
        status = path.lstat()
    except FileNotFoundError as error:
        raise UnsafeStoragePathError(f"storage directory disappeared: {path}") from error
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise UnsafeStoragePathError(f"storage directory is not a real directory: {path}")


def _open_directory(path: Path) -> int:
    try:
        descriptor = os.open(path, _DIRECTORY_FLAGS)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise UnsafeStoragePathError(f"cannot safely open storage directory: {path}") from error
    status = os.fstat(descriptor)
    if not stat.S_ISDIR(status.st_mode):
        os.close(descriptor)
        raise UnsafeStoragePathError(f"storage path is not a directory: {path}")
    return descriptor


def _write_all(descriptor: int, chunk: bytes) -> None:
    view = memoryview(chunk)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write while publishing CAS blob")
        view = view[written:]


def _iter_stream(stream: BinaryIO | Iterable[bytes], chunk_size: int) -> Iterator[bytes]:
    if hasattr(stream, "read"):
        reader = cast(BinaryIO, stream)
        while True:
            chunk = reader.read(chunk_size)
            if not isinstance(chunk, bytes):
                raise TypeError("binary stream read() must return bytes")
            if not chunk:
                return
            yield chunk
    else:
        for chunk in stream:
            if not isinstance(chunk, bytes):
                raise TypeError("stream chunks must be bytes")
            if chunk:
                yield chunk


class LocalCAS:
    """Immutable SHA-256 content-addressed storage on one local filesystem.

    Publication uses a randomized, exclusively-created temporary file and an atomic hard link.
    Existing addresses are verified rather than overwritten. Canonical blob paths contain only
    the digest-derived shard and digest suffix.
    """

    def __init__(self, root: Path | str, *, default_max_bytes: int = 256 * 1024 * 1024) -> None:
        if isinstance(default_max_bytes, bool) or default_max_bytes < 0:
            raise ValueError("default_max_bytes must be a non-negative integer")
        self.root = Path(root).expanduser().absolute()
        self.default_max_bytes = default_max_bytes
        self._temporary_root = self.root / ".tmp"
        self._blob_root = self.root / "blobs"
        self._digest_root = self._blob_root / "sha256"
        _ensure_directory(self.root)
        _ensure_directory(self._temporary_root)
        _ensure_directory(self._blob_root)
        _ensure_directory(self._digest_root)

    def path_for(self, digest: str) -> Path:
        normalized = _normalize_digest(digest)
        return self._digest_root / normalized[:2] / normalized[2:]

    def put_bytes(self, content: bytes, *, max_bytes: int | None = None) -> StoredBlob:
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        return self.put_stream((content,), max_bytes=max_bytes)

    def put_path(self, source_path: Path | str, *, max_bytes: int | None = None) -> StoredBlob:
        path = Path(source_path)
        try:
            path_status = path.lstat()
        except FileNotFoundError as error:
            raise UnsafeStoragePathError(f"source file does not exist: {path}") from error
        if stat.S_ISLNK(path_status.st_mode):
            raise UnsafeStoragePathError("refusing to ingest a symlink")
        if not stat.S_ISREG(path_status.st_mode):
            raise UnsafeStoragePathError("refusing to ingest a non-regular file")

        try:
            descriptor = os.open(path, _READ_FLAGS)
        except OSError as error:
            raise UnsafeStoragePathError(f"cannot safely open source file: {path}") from error
        try:
            opened_status = os.fstat(descriptor)
            if not stat.S_ISREG(opened_status.st_mode):
                raise UnsafeStoragePathError("refusing to ingest a non-regular file")
            if (path_status.st_dev, path_status.st_ino) != (
                opened_status.st_dev,
                opened_status.st_ino,
            ):
                raise UnsafeStoragePathError("source file changed while it was being opened")
            with os.fdopen(descriptor, "rb", closefd=False) as source:
                return self.put_stream(source, max_bytes=max_bytes)
        finally:
            os.close(descriptor)

    def put_stream(
        self,
        stream: BinaryIO | Iterable[bytes],
        *,
        max_bytes: int | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> StoredBlob:
        limit = self.default_max_bytes if max_bytes is None else max_bytes
        if isinstance(limit, bool) or limit < 0:
            raise ValueError("max_bytes must be a non-negative integer")
        if isinstance(chunk_size, bool) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")

        temporary_directory = _open_directory(self._temporary_root)
        temporary_name = f"blob-{secrets.token_hex(24)}.part"
        descriptor = -1
        try:
            descriptor = os.open(
                temporary_name,
                _CREATE_FLAGS,
                0o600,
                dir_fd=temporary_directory,
            )
            digest = hashlib.sha256()
            byte_size = 0
            for chunk in _iter_stream(stream, chunk_size):
                observed_size = byte_size + len(chunk)
                if observed_size > limit:
                    raise ByteLimitExceeded(
                        limit_bytes=limit,
                        observed_bytes=observed_size,
                    )
                digest.update(chunk)
                _write_all(descriptor, chunk)
                byte_size = observed_size
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o444)
            temporary_status = os.fstat(descriptor)
            if not stat.S_ISREG(temporary_status.st_mode) or temporary_status.st_size != byte_size:
                raise StorageIntegrityError(
                    "temporary CAS object is not a regular file of expected size"
                )

            hex_digest = digest.hexdigest()
            destination_directory_path = self._digest_root / hex_digest[:2]
            _ensure_directory(destination_directory_path)
            destination_directory = _open_directory(destination_directory_path)
            try:
                destination_name = hex_digest[2:]
                deduplicated = False
                try:
                    os.link(
                        temporary_name,
                        destination_name,
                        src_dir_fd=temporary_directory,
                        dst_dir_fd=destination_directory,
                        follow_symlinks=False,
                    )
                    os.fsync(destination_directory)
                except FileExistsError:
                    self._verify_existing(
                        destination_directory,
                        destination_name,
                        expected_digest=hex_digest,
                        expected_size=byte_size,
                    )
                    deduplicated = True
            finally:
                os.close(destination_directory)

            return StoredBlob(
                sha256=hex_digest,
                byte_size=byte_size,
                path=self.path_for(hex_digest),
                deduplicated=deduplicated,
            )
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            with suppress(FileNotFoundError):
                os.unlink(temporary_name, dir_fd=temporary_directory)
            os.close(temporary_directory)

    def _verify_existing(
        self,
        directory_descriptor: int,
        filename: str,
        *,
        expected_digest: str,
        expected_size: int,
    ) -> None:
        try:
            descriptor = os.open(filename, _READ_FLAGS, dir_fd=directory_descriptor)
        except OSError as error:
            raise StorageIntegrityError("existing CAS address cannot be opened safely") from error
        try:
            status = os.fstat(descriptor)
            if not stat.S_ISREG(status.st_mode) or status.st_size != expected_size:
                raise StorageIntegrityError("existing CAS address has the wrong type or size")
            digest = hashlib.sha256()
            with os.fdopen(descriptor, "rb", closefd=False) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected_digest:
                raise StorageIntegrityError("existing CAS address contains different bytes")
        finally:
            os.close(descriptor)

    @contextmanager
    def open_blob(self, digest: str) -> Iterator[BinaryIO]:
        normalized = _normalize_digest(digest)
        directory_path = self._digest_root / normalized[:2]
        directory_descriptor = _open_directory(directory_path)
        try:
            try:
                descriptor = os.open(normalized[2:], _READ_FLAGS, dir_fd=directory_descriptor)
            except FileNotFoundError:
                raise
            except OSError as error:
                raise UnsafeStoragePathError(
                    "CAS object cannot be opened without following links"
                ) from error
            try:
                status = os.fstat(descriptor)
                if not stat.S_ISREG(status.st_mode):
                    raise UnsafeStoragePathError("CAS object is not a regular file")
                with os.fdopen(descriptor, "rb", closefd=False) as source:
                    yield source
            finally:
                os.close(descriptor)
        finally:
            os.close(directory_descriptor)

    def read_bytes(self, digest: str, *, max_bytes: int | None = None) -> bytes:
        limit = self.default_max_bytes if max_bytes is None else max_bytes
        with self.open_blob(digest) as source:
            return read_limited(source, max_bytes=limit)

    def contains(self, digest: str) -> bool:
        try:
            with self.open_blob(digest):
                return True
        except FileNotFoundError:
            return False

    def delete_blob(self, digest: str) -> bool:
        """Delete one canonical blob without following links.

        Callers must first remove every durable database reference.  This low-level method
        deliberately accepts only a content digest and never an arbitrary path.
        """

        normalized = _normalize_digest(digest)
        directory_path = self._digest_root / normalized[:2]
        try:
            directory_descriptor = _open_directory(directory_path)
        except FileNotFoundError:
            return False
        try:
            try:
                descriptor = os.open(
                    normalized[2:], _READ_FLAGS, dir_fd=directory_descriptor
                )
            except FileNotFoundError:
                return False
            except OSError as error:
                raise UnsafeStoragePathError(
                    "CAS object cannot be removed without following links"
                ) from error
            try:
                status = os.fstat(descriptor)
                if not stat.S_ISREG(status.st_mode):
                    raise UnsafeStoragePathError("CAS object is not a regular file")
            finally:
                os.close(descriptor)
            os.unlink(normalized[2:], dir_fd=directory_descriptor)
            os.fsync(directory_descriptor)
            return True
        finally:
            os.close(directory_descriptor)


__all__ = [
    "LocalCAS",
    "StorageError",
    "StorageIntegrityError",
    "StoredBlob",
    "UnsafeStoragePathError",
]
