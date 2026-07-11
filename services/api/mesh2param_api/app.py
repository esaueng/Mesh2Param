from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from html import escape
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from .api.core import REQUEST_ID, APIError, error_response
from .api.routes import (
    artifacts_router,
    cadgraph_router,
    health_router,
    jobs_router,
    operations_router,
    patches_router,
    projects_router,
    samples_router,
    versions_router,
)
from .config import Settings
from .db import Database, Repository
from .db.models import utc_now
from .db.repository import (
    ActiveJobConflictError,
    NotFoundError,
    RevisionConflictError,
)
from .jobs import JobSupervisor
from .jobs.lock import WorkerInstanceLock
from .logging_config import configure_service_logging
from .schemas import ErrorEnvelope
from .security import (
    SecurityPolicyError,
    UploadValidationError,
    api_security_headers,
    is_origin_allowed,
    require_allowed_host,
)
from .storage import ByteLimitExceeded, LocalCAS, UnsafeNameError

LOGGER = logging.getLogger(__name__)
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    configure_service_logging(config.log_level)
    database = Database(config)
    repository = Repository(database, max_job_events=config.max_job_events)
    storage = LocalCAS(config.storage_root, default_max_bytes=config.max_upload_bytes)
    supervisor = JobSupervisor(repository, storage, config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        worker_lock: WorkerInstanceLock | None = None
        supervisor_started = False
        try:
            database.migrate()
            config.jobs_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor, probe_name = tempfile.mkstemp(prefix="ready-", dir=config.storage_root)
            with suppress(OSError):
                os.close(descriptor)
            Path(probe_name).unlink(missing_ok=True)
            app.state.storage_ready = True
            cutoff = utc_now() - timedelta(days=config.artifact_retention_days)
            orphan_digests = await asyncio.to_thread(
                repository.delete_orphan_blobs_before, cutoff
            )
            for digest in orphan_digests:
                try:
                    await asyncio.to_thread(storage.delete_blob, digest)
                except Exception:
                    LOGGER.exception("orphan_blob_cleanup_failed")
            if orphan_digests:
                LOGGER.info(
                    "orphan_blob_cleanup_complete", extra={"count": len(orphan_digests)}
                )
            if config.job_runner_mode == "embedded":
                worker_lock = WorkerInstanceLock(config.worker_lock_path)
                worker_lock.__enter__()
                await supervisor.start()
                supervisor_started = True
            yield
        finally:
            try:
                if supervisor_started:
                    await supervisor.stop()
            finally:
                if worker_lock is not None:
                    worker_lock.__exit__(None, None, None)
                database.dispose()

    app = FastAPI(
        title="Mesh2Param API",
        version="0.1.0",
        description=(
            "Local-first project, geometry-job, version, and validated artifact API for "
            "Mesh2Param. Geometry work runs in isolated spawn processes."
        ),
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        responses={
            400: {"model": ErrorEnvelope, "description": "Invalid request"},
            404: {"model": ErrorEnvelope, "description": "Resource not found"},
            409: {"model": ErrorEnvelope, "description": "State conflict"},
            412: {"model": ErrorEnvelope, "description": "Revision conflict"},
            422: {"model": ErrorEnvelope, "description": "Domain validation failure"},
            500: {"model": ErrorEnvelope, "description": "Internal service failure"},
        },
    )
    app.state.settings = config
    app.state.database = database
    app.state.repository = repository
    app.state.storage = storage
    app.state.supervisor = supervisor
    app.state.storage_ready = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "If-Match",
            "Last-Event-ID",
            "X-Mesh2Param-Filename",
            "X-Request-ID",
        ],
        expose_headers=["ETag", "Location", "X-Request-ID"],
    )

    @app.get("/docs", include_in_schema=False)
    async def local_api_docs() -> HTMLResponse:
        route_items: list[str] = []
        for path, operations in sorted(app.openapi()["paths"].items()):
            for method, operation in operations.items():
                if method not in {"delete", "get", "head", "options", "patch", "post", "put"}:
                    continue
                summary = operation.get("summary", "") if isinstance(operation, dict) else ""
                route_items.append(
                    "<li><code>"
                    + escape(method.upper())
                    + "</code> <code>"
                    + escape(path)
                    + "</code> — "
                    + escape(str(summary))
                    + "</li>"
                )
        routes = "\n".join(route_items)
        return HTMLResponse(
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Mesh2Param API docs</title></head><body>"
            "<header><h1>Mesh2Param API</h1>"
            "<p>Self-hosted endpoint index. "
            "<a href=\"/openapi.json\">OpenAPI JSON</a></p></header>"
            f"<main><h2>Endpoints</h2><ul>{routes}</ul></main></body></html>",
            headers={
                "Content-Security-Policy": (
                    "default-src 'none'; base-uri 'none'; form-action 'none'; "
                    "frame-ancestors 'none'"
                ),
                "Cache-Control": "no-store",
            },
        )

    @app.middleware("http")
    async def request_policy(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        candidate = request.headers.get("x-request-id", "")
        request.state.request_id = (
            candidate if REQUEST_ID.fullmatch(candidate) else str(uuid.uuid4())
        )
        try:
            require_allowed_host(request.headers.get("host"), config.allowed_hosts)
            origin = request.headers.get("origin")
            if (
                request.method in MUTATING_METHODS
                and origin is not None
                and not is_origin_allowed(origin, config.cors_origins)
            ):
                raise SecurityPolicyError(
                    "origin_not_allowed", "request origin is not allowed"
                )
            response = await call_next(request)
        except SecurityPolicyError as exc:
            response = error_response(
                request,
                APIError(
                    403,
                    exc.code,
                    "Request security policy rejected the request",
                    exc.detail,
                    recoverable=False,
                ),
            )
        response.headers["X-Request-ID"] = request.state.request_id
        for name, value in api_security_headers(tls=request.url.scheme == "https").items():
            response.headers.setdefault(name, value)
        return response

    @app.exception_handler(APIError)
    async def api_error(request: Request, exc: APIError) -> JSONResponse:
        return error_response(request, exc)

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return error_response(
            request,
            APIError(404, "not_found", "Resource not found", str(exc), recoverable=False),
        )

    @app.exception_handler(RevisionConflictError)
    async def revision_conflict(
        request: Request, exc: RevisionConflictError
    ) -> JSONResponse:
        return error_response(
            request,
            APIError(
                412,
                "project_revision_conflict",
                "Project revision is stale",
                f"The current project revision is {exc.current_revision}.",
                recoverable=True,
                recommended_action="Reload the project, compare changes, and retry explicitly.",
                headers={"ETag": f'"rev-{exc.current_revision}"'},
            ),
        )

    @app.exception_handler(ActiveJobConflictError)
    async def active_conflict(
        request: Request, exc: ActiveJobConflictError
    ) -> JSONResponse:
        return error_response(
            request,
            APIError(
                409,
                "active_project_job",
                "Project has an active operation",
                str(exc),
                recoverable=True,
                recommended_action="Wait for or cancel the active operation before retrying.",
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation(
        request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request,
            APIError(
                422,
                "invalid_request",
                "Request validation failed",
                "One or more request fields are missing, unknown, or invalid.",
                recoverable=True,
                recommended_action="Correct the request fields and retry.",
            ),
        )

    @app.exception_handler(ValidationError)
    async def domain_validation(
        request: Request, _exc: ValidationError
    ) -> JSONResponse:
        return error_response(
            request,
            APIError(
                422,
                "unsupported_project_schema",
                "Domain document validation failed",
                "The CADGraph or project document does not satisfy the current strict schema.",
                recoverable=True,
                recommended_action="Migrate or correct the document before retrying.",
            ),
        )

    @app.exception_handler(UnsafeNameError)
    async def unsafe_name(request: Request, exc: UnsafeNameError) -> JSONResponse:
        return error_response(
            request,
            APIError(422, "unsafe_filename", "Filename is unsafe", str(exc), recoverable=True),
        )

    @app.exception_handler(ByteLimitExceeded)
    async def byte_limit(request: Request, exc: ByteLimitExceeded) -> JSONResponse:
        return error_response(
            request,
            APIError(
                413,
                "file_too_large",
                "Upload exceeds the byte limit",
                str(exc),
                recoverable=True,
            ),
        )

    @app.exception_handler(UploadValidationError)
    async def upload_validation(
        request: Request, exc: UploadValidationError
    ) -> JSONResponse:
        status = 413 if "limit" in exc.code else 415 if exc.code in {
            "archive_not_allowed",
            "executable_not_allowed",
            "unsupported_extension",
            "format_mismatch",
        } else 422
        return error_response(
            request,
            APIError(
                status,
                exc.code,
                "Mesh upload was rejected",
                exc.detail,
                recoverable=True,
                recommended_action="Choose a valid bounded STL, OBJ, or PLY mesh.",
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception(
            "unhandled_api_error",
            extra={"request_id": request.state.request_id, "exception_type": type(exc).__name__},
        )
        return error_response(
            request,
            APIError(
                500,
                "internal_error",
                "Internal service error",
                "The request could not be completed. The full trace is available in server logs.",
                recoverable=True,
                recommended_action="Retry once; inspect server logs if the failure repeats.",
            ),
        )

    for router in (
        projects_router,
        operations_router,
        patches_router,
        cadgraph_router,
        versions_router,
        artifacts_router,
        jobs_router,
        samples_router,
        health_router,
    ):
        app.include_router(router)
    return app


__all__ = ["create_app"]
