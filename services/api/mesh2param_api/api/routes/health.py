from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ...config import Settings
from ...db.session import Database
from ...jobs import JobSupervisor
from ...jobs.heartbeat import worker_heartbeat_is_fresh
from ..core import success
from ..dependencies import settings, supervisor

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> JSONResponse:
    return success(request, {"status": "ok"})


@router.get("/ready")
def ready(
    request: Request,
    worker: JobSupervisor = Depends(supervisor),
    config: Settings = Depends(settings),
) -> JSONResponse:
    database: Database = request.app.state.database
    storage_ready = request.app.state.storage_ready
    database_ready = database.ready()
    worker_ready = (
        worker.healthy
        if config.job_runner_mode == "embedded"
        else worker_heartbeat_is_fresh(
            config.worker_heartbeat_path,
            max_age_seconds=config.worker_heartbeat_stale_seconds,
        )
    )
    ready_now = database_ready and worker_ready and storage_ready
    return success(
        request,
        {
            "status": "ready" if ready_now else "not-ready",
            "database": database_ready,
            "storage": storage_ready,
            "supervisor": worker_ready,
            "runnerMode": config.job_runner_mode,
        },
        status_code=200 if ready_now else 503,
    )


__all__ = ["router"]
