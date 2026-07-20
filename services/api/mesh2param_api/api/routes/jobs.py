from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from ...config import Settings
from ...db import Repository
from ...db.models import JobStatus
from ...schemas import JobEnvelope, JobListEnvelope
from ..core import APIError, request_id, success
from ..dependencies import repository, settings

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=JobListEnvelope)
def list_jobs(
    request: Request,
    project_id: str | None = Query(default=None, alias="projectId"),
    status: JobStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repo: Repository = Depends(repository),
) -> JSONResponse:
    status_value = status.value if status is not None else None
    jobs = repo.list_jobs(
        project_id=project_id, status=status_value, limit=limit, offset=offset
    )
    total = repo.count_jobs(project_id=project_id, status=status_value)
    return success(request, {
        "items": jobs, "total": total, "limit": limit, "offset": offset,
        "hasMore": offset + len(jobs) < total,
    })


@router.get("/{job_id}", response_model=JobEnvelope)
def get_job(
    request: Request,
    job_id: str,
    repo: Repository = Depends(repository),
) -> JSONResponse:
    return success(request, repo.get_job(job_id))


@router.post("/{job_id}/cancel", response_model=JobEnvelope)
def cancel_job(
    request: Request,
    job_id: str,
    repo: Repository = Depends(repository),
) -> JSONResponse:
    job = repo.request_cancel(job_id)
    repo.record_audit(
        request_id(request),
        "job.cancel",
        "accepted",
        project_id=str(job["projectId"]),
        job_id=job_id,
    )
    return success(request, job, status_code=202 if job["status"] == "running" else 200)


@router.delete("/{job_id}", status_code=204)
def delete_job(
    request: Request,
    job_id: str,
    repo: Repository = Depends(repository),
) -> Response:
    repo.record_audit(request_id(request), "job.delete", "success", job_id=job_id)
    repo.delete_terminal_job(job_id)
    return Response(status_code=204)


@router.get("/{job_id}/events")
async def job_events(
    request: Request,
    job_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    repo: Repository = Depends(repository),
    config: Settings = Depends(settings),
) -> StreamingResponse:
    await asyncio.to_thread(repo.get_job, job_id)
    try:
        cursor = 0 if last_event_id is None else int(last_event_id)
        if cursor < 0:
            raise ValueError
    except ValueError as exc:
        raise APIError(
            400,
            "invalid_event_cursor",
            "Invalid event cursor",
            "Last-Event-ID must be a non-negative integer.",
            job_id=job_id,
            recoverable=True,
        ) from exc

    async def stream() -> AsyncIterator[str]:
        nonlocal cursor
        loop = asyncio.get_running_loop()
        keepalive_at = loop.time()
        yield "retry: 2000\n\n"
        while True:
            if await request.is_disconnected():
                return
            events, terminal = await asyncio.to_thread(repo.events_after, job_id, cursor)
            for event in events:
                cursor = int(event["id"])
                payload = json.dumps(
                    event["data"], separators=(",", ":"), ensure_ascii=True, allow_nan=False
                )
                yield f"id: {cursor}\nevent: {event['event']}\ndata: {payload}\n\n"
            if terminal and not events:
                return
            now = loop.time()
            if not events and now - keepalive_at >= config.sse_keepalive_seconds:
                yield ": keep-alive\n\n"
                keepalive_at = now
            await asyncio.sleep(config.sse_poll_seconds)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
