from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path

import pytest
from mesh2param.samples import sample_graph
from mesh2param_api.api.routes.operations import _operation_payload
from mesh2param_api.config import Settings
from mesh2param_api.db import Database, JobStatus, Repository
from mesh2param_api.db.models import utc_now
from mesh2param_api.logging_config import JsonFormatter
from mesh2param_api.schemas import OperationRequest
from mesh2param_api.storage import LocalCAS


def test_settings_do_not_auto_load_container_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in (
        "MESH2PARAM_ENVIRONMENT",
        "MESH2PARAM_DATA_DIR",
        "MESH2PARAM_JOB_RUNNER_MODE",
    ):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "MESH2PARAM_ENVIRONMENT=production\n"
        "MESH2PARAM_DATA_DIR=/var/lib/mesh2param\n"
        "MESH2PARAM_JOB_RUNNER_MODE=external\n",
        encoding="utf-8",
    )

    settings = Settings()

    assert settings.environment == "development"
    assert settings.data_dir == Path(".mesh2param-data")
    assert settings.job_runner_mode == "embedded"


def test_exact_environment_names_and_production_guards(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "configured.sqlite3"
    storage_path = tmp_path / "configured-storage"
    values = {
        "MESH2PARAM_ENVIRONMENT": "test",
        "MESH2PARAM_DATABASE_URL": f"sqlite:///{database_path}",
        "MESH2PARAM_STORAGE_PATH": str(storage_path),
        "MESH2PARAM_PUBLIC_URL": "https://mesh2param.invalid",
        "MESH2PARAM_API_URL": "https://mesh2param.invalid/api",
        "MESH2PARAM_MAX_UPLOAD_MB": "12",
        "MESH2PARAM_MAX_TRIANGLES": "1234",
        "MESH2PARAM_JOB_TIMEOUT_SECONDS": "45",
        "MESH2PARAM_RETENTION_DAYS": "9",
        "MESH2PARAM_CORS_ORIGINS": "http://localhost:5173,http://127.0.0.1:5173",
        "MESH2PARAM_WORKER_COUNT": "3",
        "MESH2PARAM_LOG_LEVEL": "WARNING",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.resolved_database_url == f"sqlite:///{database_path}"
    assert settings.storage_root == storage_path
    assert settings.s3_endpoint is None
    assert settings.s3_bucket is None
    assert settings.queue_url is None
    assert settings.public_url == "https://mesh2param.invalid"
    assert settings.api_url == "https://mesh2param.invalid/api"
    assert settings.max_upload_bytes == 12 * 1024 * 1024
    assert settings.max_triangles == 1234
    assert settings.worker_timeout_seconds == 45
    assert settings.artifact_retention_days == 9
    assert settings.worker_concurrency == 3
    assert settings.log_level == "WARNING"

    with pytest.raises(ValueError, match="wildcard"):
        Settings(  # type: ignore[call-arg]
            environment="production", cors_origins=("*",), _env_file=None
        )
    with pytest.raises(ValueError, match="S3 storage is not implemented"):
        Settings(s3_endpoint="https://s3.invalid", _env_file=None)  # type: ignore[call-arg]


def test_production_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    production = {
        "environment": "production",
        "data_dir": tmp_path,
        "storage_path": tmp_path / "storage",
        "database_url": f"sqlite:///{tmp_path / 'mesh2param.sqlite3'}",
        "public_url": "https://mesh2param.invalid",
        "api_url": "http://api:8000/api",
        "cors_origins": '["https://mesh2param.invalid"]',
        "allowed_hosts": "mesh2param.invalid,api",
        "job_runner_mode": "external",
        "worker_count": 1,
        "_env_file": None,
    }
    settings = Settings(**production)  # type: ignore[arg-type]
    assert settings.cors_origins == ("https://mesh2param.invalid",)
    assert settings.allowed_hosts == ("mesh2param.invalid", "api")
    assert settings.public_url == "https://mesh2param.invalid"
    assert settings.api_url == "http://api:8000/api"
    same_origin_values = dict(production)
    same_origin_values.update(cors_origins="[]", s3_endpoint="", queue_url="")
    same_origin = Settings(**same_origin_values)  # type: ignore[arg-type]
    assert same_origin.cors_origins == ()
    assert same_origin.s3_endpoint is None and same_origin.queue_url is None

    with pytest.raises(ValueError, match="extra_forbidden"):
        Settings(  # type: ignore[call-arg]
            environment="test", typo_setting=True, _env_file=None
        )
    monkeypatch.setenv("MESH2PARAM_WORKER_COUNTT", "1")
    with pytest.raises(ValueError, match="unknown Mesh2Param environment settings"):
        Settings(**production)  # type: ignore[arg-type]
    monkeypatch.delenv("MESH2PARAM_WORKER_COUNTT")

    for override, message in (
        ({"data_dir": Path("relative-data")}, "DATA_DIR must be absolute"),
        ({"database_url": "sqlite:///relative.sqlite3"}, "absolute path"),
        ({"debug": True}, "debug must be disabled"),
        ({"log_level": "DEBUG"}, "DEBUG logging"),
        ({"worker_count": 2}, "exactly one geometry worker"),
        ({"cors_origins": "https://mesh2param.invalid/path"}, "invalid HTTP security"),
        ({"allowed_hosts": "api/invalid"}, "invalid HTTP security"),
        ({"public_url": "file:///tmp/app"}, r"HTTP\(S\) URL"),
        ({"api_url": "https://user:secret@api.invalid"}, "without credentials"),
        ({"s3_endpoint": "https://s3.invalid"}, "S3 storage is not implemented"),
        ({"queue_url": "redis://queue.invalid/0"}, "queue is not implemented"),
    ):
        with pytest.raises(ValueError, match=message):
            Settings(**{**production, **override})  # type: ignore[arg-type]

    real_storage = tmp_path / "real-storage"
    real_storage.mkdir()
    linked_storage = tmp_path / "linked-storage"
    linked_storage.symlink_to(real_storage, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink components"):
        Settings(**{**production, "storage_path": linked_storage / "cas"})  # type: ignore[arg-type]

    derived_data = tmp_path / "derived-data"
    derived_data.mkdir()
    (derived_data / "storage").symlink_to(real_storage, target_is_directory=True)
    derived_values = {**production, "data_dir": derived_data, "storage_path": None}
    with pytest.raises(ValueError, match="storage directory"):
        Settings(**derived_values)  # type: ignore[arg-type]

    database_data = tmp_path / "database-data"
    database_data.mkdir()
    database_target = tmp_path / "database-target.sqlite3"
    database_target.touch()
    (database_data / "mesh2param.sqlite3").symlink_to(database_target)
    database_values = {
        **production,
        "data_dir": database_data,
        "database_url": None,
        "storage_path": real_storage,
    }
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(**database_values)  # type: ignore[arg-type]


def test_repository_revision_queue_attempt_and_durable_events(tmp_path: Path) -> None:
    settings = Settings(  # type: ignore[call-arg]
        environment="test", data_dir=tmp_path, _env_file=None
    )
    database = Database(settings)
    database.migrate()
    repo = Repository(database)
    try:
        project = repo.create_project("DB contract", "mm")
        updated = repo.update_project(
            project["id"], project["revision"], name="Updated", units=None
        )
        assert updated["revision"] == 2
        with pytest.raises(Exception, match="project revision"):
            repo.update_project(project["id"], 1, name="stale", units=None)

        job = repo.create_job(
            project["id"],
            updated["revision"],
            "test_hang",
            {"inputHash": "a" * 64, "settings": {}},
            timeout_seconds=2,
        )
        claimed = repo.claim_one()
        assert claimed is not None and claimed["id"] == job["id"]
        assert repo.apply_worker_event(
            job["id"],
            claimed["attemptId"],
            claimed["runToken"],
            {"type": "progress", "phase": "loading mesh", "progress": 25},
        )
        assert repo.terminalize_job(
            job["id"],
            claimed["attemptId"],
            claimed["runToken"],
            status=JobStatus.CANCELLED,
            code="job_cancelled",
            summary="cancelled",
            detail="cancelled in test",
            phase="cancelled",
            recoverable=True,
            recommended_action=None,
        )
        events, terminal = repo.events_after(job["id"], 0)
        assert terminal
        assert [event["id"] for event in events] == sorted(event["id"] for event in events)
        assert [event["event"] for event in events][-1] == "cancelled"
        assert repo.get_job(job["id"])["progress"] == 25

        abandoned = repo.create_job(
            project["id"],
            updated["revision"],
            "test_hang",
            {"inputHash": "f" * 64, "settings": {}},
            timeout_seconds=2,
        )
        abandoned_claim = repo.claim_one()
        assert abandoned_claim is not None and abandoned_claim["id"] == abandoned["id"]
        assert repo.recover_abandoned() == 1
        recovered = repo.get_job(abandoned["id"])
        assert recovered["status"] == "failed"
        assert recovered["error"]["code"] == "worker_abandoned"
    finally:
        database.dispose()


def test_graph_operation_cache_identity_is_canonical(tmp_path: Path) -> None:
    graph = sample_graph("rectangular-block").model_dump(mode="json", by_alias=True)
    reordered = dict(reversed(list(graph.items())))
    project_a: dict[str, object] = {
        "id": "project.cache",
        "name": "Cache",
        "units": "mm",
        "state": {"cadgraph": graph, "source": None, "currentVersionId": None},
    }
    project_b: dict[str, object] = {
        **project_a,
        "state": {"currentVersionId": None, "source": None, "cadgraph": reordered},
    }
    store = LocalCAS(tmp_path / "storage")
    body = OperationRequest()
    first = _operation_payload(project_a, "rebuild", body, store)
    second = _operation_payload(project_b, "rebuild", body, store)
    assert first["inputHash"] == second["inputHash"]
    assert len(str(first["inputHash"])) == 64


def test_event_history_is_bounded_and_orphan_blobs_are_retained_then_cleaned(
    tmp_path: Path,
) -> None:
    settings = Settings(  # type: ignore[call-arg]
        environment="test", data_dir=tmp_path, _env_file=None
    )
    database = Database(settings)
    database.migrate()
    repo = Repository(database, max_job_events=3)
    store = LocalCAS(settings.storage_root)
    try:
        project = repo.create_project("Retention", "mm")
        blob = store.put_bytes(b"solid empty\nendsolid empty\n")
        _, revision = repo.create_source_asset(
            project["id"],
            project["revision"],
            original_filename="empty.stl",
            format_name="stl",
            encoding="ascii",
            blob={
                "sha256": blob.sha256,
                "byteSize": blob.byte_size,
                "mediaType": "model/stl",
                "storageKey": str(blob.path.relative_to(store.root)),
            },
            declared_units="mm",
            units_confirmed=True,
            scale_factor=1.0,
        )
        job = repo.create_job(
            project["id"],
            revision,
            "test_hang",
            {"inputHash": "9" * 64, "settings": {}},
            timeout_seconds=10,
        )
        claimed = repo.claim_one()
        assert claimed is not None
        for index in range(8):
            assert repo.apply_worker_event(
                job["id"],
                claimed["attemptId"],
                claimed["runToken"],
                {"type": "progress", "phase": "bounded", "progress": index},
            )
        assert repo.terminalize_job(
            job["id"],
            claimed["attemptId"],
            claimed["runToken"],
            status=JobStatus.CANCELLED,
            code="job_cancelled",
            summary="cancelled",
            detail="cancelled in bounded-log test",
            phase="cancelled",
            recoverable=True,
            recommended_action=None,
        )
        events, terminal = repo.events_after(job["id"], 0)
        assert terminal and len(events) == 3
        assert events[-1]["event"] == "cancelled"

        repo.delete_project(project["id"])
        orphaned = repo.delete_orphan_blobs_before(utc_now() + timedelta(seconds=1))
        assert orphaned == [blob.sha256]
        assert store.delete_blob(blob.sha256)
    finally:
        database.dispose()


def test_structured_log_formatter_has_correlation_fields() -> None:
    record = logging.LogRecord(
        "mesh2param_api.test", logging.INFO, __file__, 1, "phase complete", (), None
    )
    record.request_id = "request-1"
    record.project_id = "project-1"
    record.job_id = "job-1"
    record.phase = "building B-Rep"
    document = json.loads(JsonFormatter().format(record))
    assert document["requestId"] == "request-1"
    assert document["jobId"] == "job-1"
    assert document["phase"] == "building B-Rep"
