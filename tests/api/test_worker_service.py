from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from mesh2param_api import Settings, create_app
from mesh2param_api.db import Database, Repository
from mesh2param_api.jobs.heartbeat import (
    read_worker_heartbeat,
    worker_heartbeat_is_fresh,
    write_worker_heartbeat,
)
from mesh2param_api.jobs.service import (
    WorkerAlreadyRunningError,
    WorkerInstanceLock,
    healthcheck,
    run_worker_service,
)
from mesh2param_api.jobs.supervisor import JobSupervisor


def external_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "data_dir": tmp_path,
        "job_runner_mode": "external",
        "worker_count": 1,
        "worker_poll_seconds": 0.02,
        "worker_cancel_grace_seconds": 0.1,
        "worker_heartbeat_seconds": 0.1,
        "worker_heartbeat_stale_seconds": 1.0,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_worker_heartbeat_is_strict_atomic_and_stale_aware(tmp_path: Path) -> None:
    path = tmp_path / "worker-heartbeat.json"
    now = time.time()
    heartbeat = write_worker_heartbeat(
        path,
        status="ready",
        pid=os.getpid(),
        started_at=now - 10,
        now=now,
    )
    assert read_worker_heartbeat(path) == heartbeat
    assert worker_heartbeat_is_fresh(path, max_age_seconds=5, now=now + 4.9)
    assert not worker_heartbeat_is_fresh(path, max_age_seconds=5, now=now + 5.1)

    write_worker_heartbeat(
        path,
        status="stopping",
        pid=os.getpid(),
        started_at=now - 10,
        now=now,
    )
    assert not worker_heartbeat_is_fresh(path, max_age_seconds=5, now=now)
    path.write_text('{"unexpected":true}\n', encoding="utf-8")
    assert read_worker_heartbeat(path) is None
    path.write_text(
        '{"heartbeatAt":NaN,"pid":1,"schemaVersion":1,"startedAt":1,'
        '"status":"ready"}\n',
        encoding="utf-8",
    )
    assert read_worker_heartbeat(path) is None
    path.unlink()
    target = tmp_path / "heartbeat-target"
    target.write_text("{}\n", encoding="utf-8")
    path.symlink_to(target)
    assert read_worker_heartbeat(path) is None


def test_worker_instance_lock_enforces_one_sqlite_supervisor(tmp_path: Path) -> None:
    lock_path = tmp_path / "worker.lock"
    with (
        WorkerInstanceLock(lock_path),
        pytest.raises(WorkerAlreadyRunningError, match="already owns"),
        WorkerInstanceLock(lock_path),
    ):
        raise AssertionError("a second worker must not acquire the lock")
    with WorkerInstanceLock(lock_path):
        assert lock_path.read_text(encoding="ascii").strip() == str(os.getpid())


def test_embedded_api_refuses_a_second_sqlite_queue_owner(tmp_path: Path) -> None:
    settings = Settings(  # type: ignore[call-arg]
        environment="test",
        data_dir=tmp_path,
        job_runner_mode="embedded",
        worker_count=1,
        _env_file=None,
    )
    with (
        WorkerInstanceLock(settings.worker_lock_path),
        pytest.raises(WorkerAlreadyRunningError, match="already owns"),
        TestClient(create_app(settings)),
    ):
        raise AssertionError("a second SQLite queue owner must not start")


def test_external_api_readiness_uses_heartbeat_without_claiming_jobs(
    tmp_path: Path,
) -> None:
    settings = external_settings(tmp_path)
    now = time.time()
    write_worker_heartbeat(
        settings.worker_heartbeat_path,
        status="ready",
        pid=os.getpid(),
        started_at=now,
        now=now,
    )
    with TestClient(create_app(settings)) as client:
        readiness = client.get("/ready")
        assert readiness.status_code == 200
        assert readiness.json()["data"] == {
            "status": "ready",
            "database": True,
            "storage": True,
            "supervisor": True,
            "runnerMode": "external",
        }
        repo = cast(Any, client.app).state.repository
        project = repo.create_project("External runner", "mm")
        job = repo.create_job(
            project["id"],
            project["revision"],
            "test_hang",
            {"inputHash": "f" * 64, "settings": {}},
            timeout_seconds=30,
        )
        time.sleep(0.1)
        assert repo.get_job(job["id"])["status"] == "queued"

        write_worker_heartbeat(
            settings.worker_heartbeat_path,
            status="ready",
            pid=os.getpid(),
            started_at=now,
            now=now - 10,
        )
        stale = client.get("/ready")
        assert stale.status_code == 503
        assert stale.json()["data"]["supervisor"] is False


def test_standalone_worker_gracefully_terminalizes_active_job(tmp_path: Path) -> None:
    settings = external_settings(tmp_path)
    database = Database(settings)
    database.migrate()
    repository = Repository(database)
    project = repository.create_project("Graceful worker shutdown", "mm")
    job = repository.create_job(
        project["id"],
        project["revision"],
        "test_hang",
        {"inputHash": "e" * 64, "settings": {}},
        timeout_seconds=30,
        max_attempts=1,
    )

    async def exercise() -> None:
        stop_event = asyncio.Event()
        service = asyncio.create_task(
            run_worker_service(
                settings,
                stop_event=stop_event,
                install_signal_handlers=False,
            )
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = await asyncio.to_thread(repository.get_job, job["id"])
            if current["status"] == "running" and healthcheck(settings) == 0:
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("standalone worker did not claim the queued job")
        stop_event.set()
        assert await asyncio.wait_for(service, timeout=10) == 0

    try:
        asyncio.run(exercise())
        stopped = repository.get_job(job["id"])
        assert stopped["status"] == "failed"
        assert stopped["error"]["code"] == "service_shutdown"
        assert healthcheck(settings) == 1
        heartbeat = read_worker_heartbeat(settings.worker_heartbeat_path)
        assert heartbeat is not None and heartbeat["status"] == "stopped"
    finally:
        database.dispose()


def test_standalone_worker_stops_heartbeat_when_supervisor_crashes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = external_settings(tmp_path)

    async def crash_supervisor(_supervisor: JobSupervisor) -> None:
        raise RuntimeError("simulated supervisor crash")

    monkeypatch.setattr(JobSupervisor, "_run", crash_supervisor)
    with pytest.raises(RuntimeError, match="supervisor stopped unexpectedly"):
        asyncio.run(
            run_worker_service(settings, install_signal_handlers=False)
        )
    assert healthcheck(settings) == 1
    heartbeat = read_worker_heartbeat(settings.worker_heartbeat_path)
    assert heartbeat is not None and heartbeat["status"] == "stopped"
