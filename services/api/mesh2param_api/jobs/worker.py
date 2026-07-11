from __future__ import annotations

import json
import os
import resource
import shutil
import stat
import sys
import time
import traceback
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from .handlers import JobFailure, run_handler
from .protocol import MAX_RESULT_BYTES, WorkerEvent, encode_event

RESULT_FILE = ".mesh2param-job-output.json"


class WorkerCancelled(RuntimeError):
    pass


def _send(connection: Connection, event: WorkerEvent) -> None:
    connection.send_bytes(encode_event(event))


def _safe_environment(workdir: Path) -> None:
    retained = {
        key: value
        for key, value in os.environ.items()
        if key in {"LANG", "LC_ALL", "TZ", "PYTHONPATH", "DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH"}
    }
    os.environ.clear()
    os.environ.update(retained)
    os.environ.update(
        {
            "HOME": str(workdir),
            "TMPDIR": str(workdir),
            "XDG_CACHE_HOME": str(workdir / ".cache"),
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )


def _resource_limits(timeout_seconds: float, memory_bytes: int) -> None:
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        soft_cpu = max(1, int(timeout_seconds) + 1)
        hard_cpu = soft_cpu + 2
        resource.setrlimit(resource.RLIMIT_CPU, (soft_cpu, hard_cpu))
        resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024**3, 2 * 1024**3))
        current_nofile = resource.getrlimit(resource.RLIMIT_NOFILE)
        descriptor_limit = min(current_nofile[1], 256)
        resource.setrlimit(resource.RLIMIT_NOFILE, (descriptor_limit, descriptor_limit))
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    except (OSError, ValueError):
        # Parent wall-clock timeout and container cgroups remain authoritative.
        pass


def _disable_outbound_network() -> None:
    """Reject Python socket connection and name-resolution attempts in production workers."""

    blocked_events = {
        "socket.connect",
        "socket.connect_ex",
        "socket.getaddrinfo",
        "socket.gethostbyaddr",
        "socket.gethostbyname",
    }

    def reject_network(event: str, _arguments: tuple[Any, ...]) -> None:
        if event in blocked_events:
            raise PermissionError("outbound network is disabled for geometry workers")

    sys.addaudithook(reject_network)


def _stage_source(payload: dict[str, Any], workdir: Path) -> None:
    raw_path = payload.get("sourcePath")
    if raw_path is None:
        return
    source = payload.get("source")
    format_name = source.get("format") if isinstance(source, dict) else None
    if format_name not in {"stl", "obj", "ply"}:
        raise JobFailure(
            "unsupported_file",
            "validating upload",
            "Source format is unsupported",
            "The preserved source format is not STL, OBJ, or PLY.",
            recoverable=False,
            recommended_action="Upload a supported mesh format.",
        )
    canonical = Path(str(raw_path))
    file_status = canonical.lstat()
    if stat.S_ISLNK(file_status.st_mode) or not stat.S_ISREG(file_status.st_mode):
        raise JobFailure(
            "source_missing",
            "validating upload",
            "Source mesh is unavailable",
            "The content-addressed source is not a safe regular file.",
            recoverable=True,
            recommended_action="Re-upload the unchanged source mesh.",
        )
    staged = workdir / f"source.{format_name}"
    try:
        os.link(canonical, staged, follow_symlinks=False)
    except OSError:
        shutil.copyfile(canonical, staged, follow_symlinks=False)
    payload["sourcePath"] = str(staged)


def worker_main(
    job_id: str,
    kind: str,
    payload_json: str,
    workdir_raw: str,
    send_connection: Connection,
    cancel_event: Any,
    parent_pid: int,
    timeout_seconds: float,
    memory_bytes: int,
    disable_outbound_network: bool,
) -> None:
    del job_id
    workdir = Path(workdir_raw)
    try:
        os.chdir(workdir)
        _safe_environment(workdir)
        _resource_limits(timeout_seconds, memory_bytes)
        if disable_outbound_network:
            _disable_outbound_network()
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise JobFailure(
                "invalid_job_payload",
                "starting worker",
                "Invalid worker payload",
                "The persisted job payload is not an object.",
                recoverable=False,
                recommended_action=None,
            )
        _stage_source(payload, workdir)

        previous_phase: str | None = None
        previous_started = time.perf_counter()

        def progress(phase: str, value: float, message: str | None) -> None:
            nonlocal previous_phase, previous_started
            if cancel_event.is_set() or os.getppid() != parent_pid:
                raise WorkerCancelled
            now = time.perf_counter()
            completed_phase = previous_phase
            completed_duration = (
                (now - previous_started) * 1000.0 if completed_phase is not None else None
            )
            _send(
                send_connection,
                WorkerEvent(
                    type="progress",
                    phase=phase,
                    progress=min(99.0, max(0.0, value)),
                    message=message,
                    previous_phase=completed_phase,
                    previous_phase_duration_ms=completed_duration,
                ),
            )
            previous_phase = phase
            previous_started = now

        progress("starting worker", 1.0, "Geometry worker initialized")
        output = run_handler(kind, payload, workdir, progress)
        if cancel_event.is_set():
            raise WorkerCancelled
        result_path = workdir / RESULT_FILE
        result_path.write_text(
            json.dumps(output.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False),
            encoding="utf-8",
            newline="\n",
        )
        if result_path.stat().st_size > MAX_RESULT_BYTES:
            raise JobFailure(
                "worker_result_too_large",
                "finalizing artifacts",
                "Worker result exceeded its limit",
                "The bounded worker result document was larger than the service limit.",
                recoverable=True,
                recommended_action="Reduce input complexity or patch count and retry.",
            )
        _send(
            send_connection,
            WorkerEvent(
                type="completed",
                phase="finalizing artifacts",
                progress=99.0,
                message="Worker output is ready for atomic publication",
                result_file=RESULT_FILE,
            ),
        )
    except WorkerCancelled:
        _send(
            send_connection,
            WorkerEvent(
                type="cancelled",
                phase="cancelled",
                message="Cancellation acknowledged at a safe checkpoint",
                code="job_cancelled",
                summary="Job cancelled",
                recoverable=True,
            ),
        )
    except JobFailure as exc:
        _send(
            send_connection,
            WorkerEvent(
                type="failed",
                phase=exc.phase,
                level="error",
                code=exc.code,
                summary=exc.summary,
                detail=exc.detail,
                recoverable=exc.recoverable,
                recommended_action=exc.recommended_action,
            ),
        )
    except Exception as exc:
        code = str(getattr(exc, "code", "worker_failed"))[:100]
        phase = str(getattr(exc, "stage", "worker"))[:80]
        _send(
            send_connection,
            WorkerEvent(
                type="failed",
                phase=phase,
                level="error",
                code=code,
                summary="Geometry worker failed",
                detail=str(exc)[:4000] or type(exc).__name__,
                recoverable=code not in {"unsupported_file", "triangle_limit"},
                recommended_action="Review the job detail and input limits before retrying.",
                internal_traceback=traceback.format_exc(limit=24)[-16_000:],
            ),
        )
    finally:
        send_connection.close()


__all__ = ["RESULT_FILE", "worker_main"]
