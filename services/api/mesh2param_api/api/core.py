from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

LOGGER = logging.getLogger(__name__)
REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
ETAG = re.compile(r'^(?:W/)?"rev-(\d+)"$')


class APIError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        summary: str,
        detail: str,
        *,
        phase: str | None = None,
        project_id: str | None = None,
        job_id: str | None = None,
        recoverable: bool = False,
        recommended_action: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.summary = summary
        self.detail = detail
        self.phase = phase
        self.project_id = project_id
        self.job_id = job_id
        self.recoverable = recoverable
        self.recommended_action = recommended_action
        self.headers = headers or {}


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", uuid.uuid4()))


def success(
    request: Request,
    data: Any,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {"data": data, "meta": {"requestId": request_id(request)}},
        status_code=status_code,
        headers=headers,
    )


def error_response(request: Request, error: APIError) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": error.code,
                "summary": error.summary,
                "detail": error.detail,
                "phase": error.phase,
                "projectId": error.project_id,
                "jobId": error.job_id,
                "recoverable": error.recoverable,
                "recommendedAction": error.recommended_action,
            },
            "meta": {"requestId": request_id(request)},
        },
        status_code=error.status_code,
        headers=error.headers,
    )


def parse_if_match(value: str | None) -> int:
    if value is None:
        raise APIError(
            428,
            "precondition_required",
            "Project revision is required",
            'Send the current ETag in an If-Match header, for example "rev-3".',
            recoverable=True,
            recommended_action="Reload the project and retry the edit with its current ETag.",
        )
    match = ETAG.fullmatch(value.strip())
    if match is None:
        raise APIError(
            400,
            "invalid_revision_etag",
            "Invalid project revision",
            'If-Match must use the exact form "rev-N".',
            recoverable=True,
        )
    return int(match.group(1))


def revision_headers(revision: int) -> dict[str, str]:
    return {"ETag": f'"rev-{revision}"'}


__all__ = [
    "REQUEST_ID",
    "APIError",
    "error_response",
    "parse_if_match",
    "request_id",
    "revision_headers",
    "success",
]
