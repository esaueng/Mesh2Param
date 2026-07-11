from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Strict environment configuration; every setting uses ``MESH2PARAM_``."""

    model_config = SettingsConfigDict(
        env_prefix="MESH2PARAM_",
        env_file=".env",
        extra="ignore",
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
    sse_poll_seconds: float = Field(default=0.25, ge=0.02, le=5)
    sse_keepalive_seconds: float = Field(default=15.0, ge=1, le=60)
    max_job_events: int = Field(default=20_000, ge=100, le=1_000_000)
    retention_days: int = Field(default=30, ge=1, le=3650)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    debug: bool = False

    @field_validator("allowed_hosts", "cors_origins", mode="before")
    @classmethod
    def parse_csv(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @model_validator(mode="after")
    def validate_security(self) -> Settings:
        if self.environment == "production":
            if "*" in self.cors_origins:
                raise ValueError("production CORS origins cannot contain a wildcard")
            if "*" in self.allowed_hosts:
                raise ValueError("production allowed hosts cannot contain a wildcard")
            if self.debug:
                raise ValueError("debug must be disabled in production")
        if self.database_url is not None and not self.database_url.startswith("sqlite:///"):
            raise ValueError(
                "M3 implements SQLite locally; PostgreSQL is an interface-only future backend"
            )
        if (self.s3_endpoint is None) != (self.s3_bucket is None):
            raise ValueError("S3_ENDPOINT and S3_BUCKET must be configured together")
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


__all__ = ["Settings"]
