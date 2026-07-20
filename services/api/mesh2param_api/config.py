from __future__ import annotations

import json
import os
import stat
from functools import cached_property
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from .security.http import (
    SecurityPolicyError,
    parse_allowed_hosts,
    parse_allowed_origins,
)


def _http_url(value: str, *, setting: str) -> str:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"{setting} must be a valid HTTP(S) URL") from exc
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            f"{setting} must be an absolute HTTP(S) URL without credentials, query, or fragment"
        )
    return value.rstrip("/")


def _reject_symlink_components(path: Path, *, setting: str) -> None:
    """Reject existing symlink components without resolving away the evidence."""

    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            status = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(status.st_mode):
            raise ValueError(f"{setting} cannot contain symlink components: {current}")


def _sqlite_path(database_url: str) -> Path:
    return Path(database_url.removeprefix("sqlite:///"))


class Settings(BaseSettings):
    """Strict environment configuration; every setting uses ``MESH2PARAM_``."""

    model_config = SettingsConfigDict(
        env_prefix="MESH2PARAM_",
        extra="forbid",
        case_sensitive=False,
        validate_default=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    data_dir: Path = Path(".mesh2param-data")
    database_url: str | None = None
    storage_path: Path | None = None
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    queue_url: str | None = None
    public_url: str | None = None
    api_url: str = "http://127.0.0.1:8000"
    storage_backend: Literal["filesystem"] = "filesystem"
    queue_backend: Literal["local"] = "local"
    job_runner_mode: Literal["embedded", "external"] = "embedded"
    bind_host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    allowed_hosts: Annotated[tuple[str, ...], NoDecode] = (
        "127.0.0.1",
        "localhost",
        "testserver",
    )
    cors_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    max_upload_mb: int = Field(default=256, ge=1, le=100_000)
    max_triangles: int = Field(default=2_000_000, ge=1)
    max_vertices: int = Field(default=6_000_000, ge=3)
    max_abs_coordinate: float = Field(default=1_000_000_000.0, gt=0)
    max_operation_count: int = Field(default=256, ge=1, le=10_000)
    max_search_rebuilds: int = Field(default=128, ge=1, le=100_000)
    worker_count: int = Field(default=2, ge=1, le=16)
    worker_memory_mb: int = Field(default=4096, ge=256, le=131_072)
    job_timeout_seconds: float = Field(default=300.0, ge=0.1, le=86_400)
    worker_cancel_grace_seconds: float = Field(default=2.0, ge=0.05, le=30)
    worker_poll_seconds: float = Field(default=0.05, ge=0.01, le=2)
    worker_heartbeat_seconds: float = Field(default=2.0, ge=0.1, le=60)
    worker_heartbeat_stale_seconds: float = Field(default=15.0, ge=1, le=300)
    sse_poll_seconds: float = Field(default=0.25, ge=0.02, le=5)
    sse_keepalive_seconds: float = Field(default=15.0, ge=1, le=60)
    max_job_events: int = Field(default=20_000, ge=100, le=1_000_000)
    retention_days: int = Field(default=30, ge=1, le=3650)
    garbage_collection_interval_seconds: float = Field(default=3600, ge=10, le=86400)
    garbage_collection_batch_size: int = Field(default=500, ge=1, le=10000)
    api_token: SecretStr | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    debug: bool = False

    @field_validator(
        "database_url",
        "storage_path",
        "s3_endpoint",
        "s3_bucket",
        "queue_url",
        "public_url",
        "api_token",
        mode="before",
    )
    @classmethod
    def blank_optional_value_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("allowed_hosts", "cors_origins", mode="before")
    @classmethod
    def parse_csv(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    decoded = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError("expected a comma-delimited string or JSON array") from exc
                if not isinstance(decoded, list) or not all(
                    isinstance(item, str) for item in decoded
                ):
                    raise ValueError("expected a JSON array of strings")
                return tuple(item.strip() for item in decoded if item.strip())
            return tuple(item.strip() for item in stripped.split(",") if item.strip())
        return value

    @field_validator("public_url", "api_url")
    @classmethod
    def validate_urls(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        field_name = info.field_name or "URL"
        return _http_url(value, setting=f"MESH2PARAM_{field_name.upper()}")

    @model_validator(mode="after")
    def validate_security(self) -> Settings:
        try:
            self.cors_origins = parse_allowed_origins(
                self.cors_origins, production=False
            )
            self.allowed_hosts = parse_allowed_hosts(
                self.allowed_hosts, production=self.environment == "production"
            )
        except SecurityPolicyError as exc:
            raise ValueError(f"invalid HTTP security configuration: {exc.detail}") from exc
        if self.environment == "production":
            known_environment_names = {
                f"MESH2PARAM_{name.upper()}" for name in type(self).model_fields
            }
            unknown_environment_names = sorted(
                name
                for name in os.environ
                if name.upper().startswith("MESH2PARAM_")
                and name.upper() not in known_environment_names
            )
            if unknown_environment_names:
                raise ValueError(
                    "unknown Mesh2Param environment settings: "
                    + ", ".join(unknown_environment_names)
                )
            if "*" in self.cors_origins:
                raise ValueError("production CORS origins cannot contain a wildcard")
            if "*" in self.allowed_hosts:
                raise ValueError("production allowed hosts cannot contain a wildcard")
            if not self.allowed_hosts:
                raise ValueError("production requires at least one explicit allowed host")
            if self.debug:
                raise ValueError("debug must be disabled in production")
            if self.log_level == "DEBUG":
                raise ValueError("DEBUG logging must be disabled in production")
            if not self.data_dir.expanduser().is_absolute():
                raise ValueError("MESH2PARAM_DATA_DIR must be absolute in production")
            _reject_symlink_components(self.data_dir, setting="MESH2PARAM_DATA_DIR")
            _reject_symlink_components(
                self.data_dir.expanduser() / "jobs", setting="Mesh2Param jobs directory"
            )
            if self.storage_path is not None:
                if not self.storage_path.expanduser().is_absolute():
                    raise ValueError("MESH2PARAM_STORAGE_PATH must be absolute in production")
                _reject_symlink_components(
                    self.storage_path, setting="MESH2PARAM_STORAGE_PATH"
                )
            else:
                _reject_symlink_components(
                    self.data_dir.expanduser() / "storage",
                    setting="Mesh2Param storage directory",
                )
        if self.database_url is not None and not self.database_url.startswith("sqlite:///"):
            raise ValueError(
                "M3 implements SQLite locally; PostgreSQL is an interface-only future backend"
            )
        if self.environment == "production":
            database_path = _sqlite_path(self.resolved_database_url)
            if not database_path.expanduser().is_absolute():
                raise ValueError("production SQLite DATABASE_URL must use an absolute path")
            _reject_symlink_components(database_path, setting="MESH2PARAM_DATABASE_URL")
        if self.s3_endpoint is not None or self.s3_bucket is not None:
            raise ValueError(
                "S3 storage is not implemented; remove S3_ENDPOINT and S3_BUCKET and use "
                "filesystem storage"
            )
        if self.queue_url is not None:
            raise ValueError(
                "a Redis-compatible queue is not implemented; remove QUEUE_URL and use the "
                "local database-backed queue"
            )
        if self.job_runner_mode == "external" and self.worker_count != 1:
            raise ValueError(
                "SQLite external runner mode requires exactly one geometry worker"
            )
        if self.worker_heartbeat_stale_seconds < self.worker_heartbeat_seconds * 2:
            raise ValueError(
                "WORKER_HEARTBEAT_STALE_SECONDS must be at least twice "
                "WORKER_HEARTBEAT_SECONDS"
            )
        return self

    @cached_property
    def resolved_data_dir(self) -> Path:
        return self.data_dir.expanduser().resolve()

    @cached_property
    def resolved_database_url(self) -> str:
        if self.database_url is not None:
            return self.database_url
        return f"sqlite:///{self.resolved_data_dir / 'mesh2param.sqlite3'}"

    @cached_property
    def storage_root(self) -> Path:
        if self.storage_path is not None:
            return self.storage_path.expanduser().resolve()
        return self.resolved_data_dir / "storage"

    @cached_property
    def jobs_root(self) -> Path:
        return self.resolved_data_dir / "jobs"

    @cached_property
    def upload_staging_root(self) -> Path:
        return self.resolved_data_dir / "upload-staging"

    @cached_property
    def worker_heartbeat_path(self) -> Path:
        return self.resolved_data_dir / "worker-heartbeat.json"

    @cached_property
    def worker_lock_path(self) -> Path:
        return self.resolved_data_dir / "worker.lock"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def worker_concurrency(self) -> int:
        return self.worker_count

    @property
    def worker_timeout_seconds(self) -> float:
        return self.job_timeout_seconds

    @property
    def artifact_retention_days(self) -> int:
        return self.retention_days

    @property
    def api_token_value(self) -> str | None:
        return self.api_token.get_secret_value() if self.api_token is not None else None


__all__ = ["Settings"]
