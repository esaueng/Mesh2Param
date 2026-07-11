from __future__ import annotations

import json
import math
import os
import stat
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Literal, TypedDict

MAX_HEARTBEAT_BYTES = 4096
WorkerServiceStatus = Literal["starting", "ready", "stopping", "stopped"]


class WorkerHeartbeat(TypedDict):
    schemaVersion: int
    status: WorkerServiceStatus
    pid: int
    startedAt: float
    heartbeatAt: float


def write_worker_heartbeat(
    path: Path,
    *,
    status: WorkerServiceStatus,
    pid: int,
    started_at: float,
    now: float | None = None,
) -> WorkerHeartbeat:
    """Atomically publish bounded worker-service liveness on the shared data volume."""

    timestamp = time.time() if now is None else now
    document: WorkerHeartbeat = {
        "schemaVersion": 1,
        "status": status,
        "pid": pid,
        "startedAt": started_at,
        "heartbeatAt": timestamp,
    }
    content = (
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")
    if len(content) > MAX_HEARTBEAT_BYTES:
        raise ValueError("worker heartbeat exceeds its bounded document size")

    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".worker-heartbeat-", dir=parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except Exception:
        with suppress(OSError):
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
        raise
    return document


def read_worker_heartbeat(path: Path) -> WorkerHeartbeat | None:
    """Read a safe, regular, strictly shaped heartbeat file."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            return None
        if status.st_size <= 0 or status.st_size > MAX_HEARTBEAT_BYTES:
            return None
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(MAX_HEARTBEAT_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(descriptor)
    if len(content) > MAX_HEARTBEAT_BYTES:
        return None
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or set(raw) != {
        "schemaVersion",
        "status",
        "pid",
        "startedAt",
        "heartbeatAt",
    }:
        return None
    if raw["schemaVersion"] != 1 or raw["status"] not in {
        "starting",
        "ready",
        "stopping",
        "stopped",
    }:
        return None
    if (
        not isinstance(raw["pid"], int)
        or isinstance(raw["pid"], bool)
        or raw["pid"] <= 0
        or not isinstance(raw["startedAt"], (int, float))
        or isinstance(raw["startedAt"], bool)
        or not isinstance(raw["heartbeatAt"], (int, float))
        or isinstance(raw["heartbeatAt"], bool)
    ):
        return None
    started_at = float(raw["startedAt"])
    heartbeat_at = float(raw["heartbeatAt"])
    if (
        not math.isfinite(started_at)
        or not math.isfinite(heartbeat_at)
        or started_at <= 0
        or heartbeat_at <= 0
    ):
        return None
    return WorkerHeartbeat(
        schemaVersion=1,
        status=raw["status"],
        pid=raw["pid"],
        startedAt=started_at,
        heartbeatAt=heartbeat_at,
    )


def worker_heartbeat_is_fresh(
    path: Path, *, max_age_seconds: float, now: float | None = None
) -> bool:
    heartbeat = read_worker_heartbeat(path)
    if heartbeat is None or heartbeat["status"] != "ready":
        return False
    timestamp = time.time() if now is None else now
    age = timestamp - heartbeat["heartbeatAt"]
    return -5.0 <= age <= max_age_seconds


__all__ = [
    "MAX_HEARTBEAT_BYTES",
    "WorkerHeartbeat",
    "WorkerServiceStatus",
    "read_worker_heartbeat",
    "worker_heartbeat_is_fresh",
    "write_worker_heartbeat",
]
