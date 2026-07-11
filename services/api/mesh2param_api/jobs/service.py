from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import time
from collections.abc import Sequence
from contextlib import suppress

from ..config import Settings
from ..db import Database, Repository
from ..logging_config import configure_service_logging
from ..storage import LocalCAS
from .heartbeat import worker_heartbeat_is_fresh, write_worker_heartbeat
from .lock import WorkerAlreadyRunningError, WorkerInstanceLock
from .supervisor import JobSupervisor

LOGGER = logging.getLogger(__name__)


def _install_signal_handlers(stop_event: asyncio.Event) -> list[signal.Signals]:
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    for name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(name, stop_event.set)
        except (NotImplementedError, RuntimeError):
            continue
        installed.append(name)
    return installed


async def _serve_until_stopped(
    settings: Settings,
    stop_event: asyncio.Event,
    supervisor: JobSupervisor,
    *,
    started_at: float,
) -> None:
    while not stop_event.is_set():
        if not supervisor.healthy:
            raise RuntimeError("standalone job supervisor stopped unexpectedly")
        await asyncio.to_thread(
            write_worker_heartbeat,
            settings.worker_heartbeat_path,
            status="ready",
            pid=os.getpid(),
            started_at=started_at,
        )
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.worker_heartbeat_seconds
            )
        except TimeoutError:
            continue


async def run_worker_service(
    settings: Settings | None = None,
    *,
    stop_event: asyncio.Event | None = None,
    install_signal_handlers: bool = True,
) -> int:
    """Run the durable database-backed queue supervisor until SIGINT/SIGTERM."""

    config = settings or Settings()
    if config.job_runner_mode != "external":
        raise ValueError(
            "the standalone worker requires MESH2PARAM_JOB_RUNNER_MODE=external"
    )
    configure_service_logging(config.log_level)
    requested_stop = stop_event or asyncio.Event()
    installed_signals: list[signal.Signals] = []
    loop = asyncio.get_running_loop()
    started_at = time.time()

    with WorkerInstanceLock(config.worker_lock_path):
        database = Database(config)
        repository = Repository(database, max_job_events=config.max_job_events)
        storage = LocalCAS(config.storage_root, default_max_bytes=config.max_upload_bytes)
        supervisor = JobSupervisor(repository, storage, config)
        supervisor_started = False
        service_error: BaseException | None = None
        try:
            if install_signal_handlers:
                installed_signals = _install_signal_handlers(requested_stop)
            database.migrate()
            config.jobs_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            await asyncio.to_thread(
                write_worker_heartbeat,
                config.worker_heartbeat_path,
                status="starting",
                pid=os.getpid(),
                started_at=started_at,
            )
            await supervisor.start()
            supervisor_started = True
            LOGGER.info("standalone_worker_ready")
            await _serve_until_stopped(
                config,
                requested_stop,
                supervisor,
                started_at=started_at,
            )
        except BaseException as exc:
            service_error = exc
        finally:
            requested_stop.set()
            try:
                await asyncio.to_thread(
                    write_worker_heartbeat,
                    config.worker_heartbeat_path,
                    status="stopping",
                    pid=os.getpid(),
                    started_at=started_at,
                )
            except BaseException as exc:
                if service_error is None:
                    service_error = exc
                else:
                    LOGGER.exception("standalone_worker_stopping_heartbeat_failed")
            if supervisor_started:
                try:
                    await supervisor.stop()
                except BaseException as exc:
                    if service_error is None:
                        service_error = exc
                    else:
                        LOGGER.exception("standalone_worker_supervisor_cleanup_failed")
            try:
                await asyncio.to_thread(
                    write_worker_heartbeat,
                    config.worker_heartbeat_path,
                    status="stopped",
                    pid=os.getpid(),
                    started_at=started_at,
                )
            except BaseException as exc:
                if service_error is None:
                    service_error = exc
                else:
                    LOGGER.exception("standalone_worker_final_heartbeat_failed")
            finally:
                database.dispose()
            for name in installed_signals:
                with suppress(NotImplementedError, RuntimeError):
                    loop.remove_signal_handler(name)
            LOGGER.info("standalone_worker_stopped")
        if service_error is not None:
            raise service_error
    return 0


def healthcheck(settings: Settings | None = None, *, max_age: float | None = None) -> int:
    config = settings or Settings()
    maximum_age = config.worker_heartbeat_stale_seconds if max_age is None else max_age
    if maximum_age <= 0:
        raise ValueError("healthcheck max age must be positive")
    return (
        0
        if worker_heartbeat_is_fresh(
            config.worker_heartbeat_path, max_age_seconds=maximum_age
        )
        else 1
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mesh2param-worker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="run the standalone geometry queue worker")
    health_parser = subparsers.add_parser(
        "healthcheck", help="check the standalone worker heartbeat"
    )
    health_parser.add_argument("--max-age", type=float)
    args = parser.parse_args(argv)
    if args.command == "healthcheck":
        return healthcheck(max_age=args.max_age)
    try:
        return asyncio.run(run_worker_service())
    except WorkerAlreadyRunningError as exc:
        LOGGER.error("standalone_worker_lock_rejected", extra={"detail": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "WorkerAlreadyRunningError",
    "WorkerInstanceLock",
    "healthcheck",
    "main",
    "run_worker_service",
]
