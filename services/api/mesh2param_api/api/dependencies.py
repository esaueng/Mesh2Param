from __future__ import annotations

from typing import cast

from fastapi import Request

from ..config import Settings
from ..db import Repository
from ..jobs import JobSupervisor
from ..storage import LocalCAS


def repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def storage(request: Request) -> LocalCAS:
    return cast(LocalCAS, request.app.state.storage)


def supervisor(request: Request) -> JobSupervisor:
    return cast(JobSupervisor, request.app.state.supervisor)


__all__ = ["repository", "settings", "storage", "supervisor"]
