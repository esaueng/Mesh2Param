from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path

import pytest
from mesh2param.samples import sample_graph
from mesh2param_api.api.core import APIError
from mesh2param_api.api.routes.operations import _operation_payload
from mesh2param_api.config import Settings
from mesh2param_api.db import Base, Database, JobStatus, Repository
from mesh2param_api.db.models import ArtifactBlob, utc_now
from mesh2param_api.logging_config import JsonFormatter
from mesh2param_api.maintenance import StorageGarbageCollector
from mesh2param_api.schemas import OperationRequest
from mesh2param_api.storage import LocalCAS
from sqlalchemy import inspect, text


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


def test_migration_creates_and_stamps_new_and_pre_alembic_databases(tmp_path: Path) -> None:
    fresh = Database(Settings(environment="test", data_dir=tmp_path / "fresh", _env_file=None))  # type: ignore[call-arg]
    try:
        fresh.migrate()
        fresh.migrate()
        assert "alembic_version" in inspect(fresh.engine).get_table_names()
        with fresh.engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version"))
            assert revision.scalar_one() == "0002_list_indexes"
        assert "ix_jobs_project_status_created" in {
            index["name"] for index in inspect(fresh.engine).get_indexes("jobs")
        }
    finally:
        fresh.dispose()

    legacy = Database(Settings(environment="test", data_dir=tmp_path / "legacy", _env_file=None))  # type: ignore[call-arg]
    try:
        Base.metadata.create_all(legacy.engine)
        legacy.migrate()
        with legacy.engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version"))
            assert revision.scalar_one() == "0002_list_indexes"
        assert "ix_projects_updated_id" in {
            index["name"] for index in inspect(legacy.engine).get_indexes("projects")
        }
    finally:
        legacy.dispose()


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

        retryable = repo.create_job(
            project["id"],
            updated["revision"],
            "test_hang",
            {"inputHash": "e" * 64, "settings": {}},
            timeout_seconds=2,
            max_attempts=2,
        )
        retryable_claim = repo.claim_one()
        assert retryable_claim is not None and retryable_claim["id"] == retryable["id"]
        assert repo.recover_abandoned() == 1
        requeued = repo.get_job(retryable["id"])
        assert requeued["status"] == "queued"
        assert requeued["attempt"] == 1
        second_claim = repo.claim_one()
        assert second_claim is not None and second_claim["attempt_count"] == 2
    finally:
        database.dispose()


def test_garbage_collection_reconciles_blobs_and_owned_temporary_paths(tmp_path: Path) -> None:
    settings = Settings(environment="test", data_dir=tmp_path, _env_file=None)  # type: ignore[call-arg]
    database = Database(settings)
    database.migrate()
    repository = Repository(database)
    storage = LocalCAS(settings.storage_root)
    try:
        orphan = storage.put_bytes(b"metadata orphan")
        with database.sessions.begin() as session:
            session.add(ArtifactBlob(
                sha256=orphan.sha256,
                byte_size=orphan.byte_size,
                media_type="application/octet-stream",
                storage_key=str(orphan.path.relative_to(storage.root)),
            ))
        unknown = storage.put_bytes(b"filesystem orphan")

        project = repository.create_project("GC active job", "mm")
        job = repository.create_job(
            project["id"], project["revision"], "gc-test", {"settings": {}},
            timeout_seconds=2,
        )
        claim = repository.claim_one()
        assert claim is not None and claim["id"] == job["id"]
        active_directory = settings.jobs_root / f"{claim['workdirToken']}-active"
        active_directory.mkdir(parents=True)
        abandoned_directory = settings.jobs_root / "abandoned-old"
        abandoned_directory.mkdir()
        settings.upload_staging_root.mkdir(parents=True)
        abandoned_upload = settings.upload_staging_root / "upload-abandoned.part"
        abandoned_upload.write_bytes(b"partial")

        result = StorageGarbageCollector(repository, storage, settings).run_once(
            cutoff=utc_now() + timedelta(seconds=1)
        )

        assert result.metadata_blobs == 1
        assert result.filesystem_blobs == 1
        assert result.job_directories == 1
        assert result.upload_files == 1
        assert not storage.contains(orphan.sha256)
        assert not storage.contains(unknown.sha256)
        assert active_directory.is_dir()
        assert not abandoned_directory.exists()
        assert not abandoned_upload.exists()
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


def test_faceted_graph_operation_stages_its_hash_bound_source(tmp_path: Path) -> None:
    store = LocalCAS(tmp_path / "storage")
    blob = store.put_bytes(b"solid source\nendsolid source\n")
    graph = sample_graph("rectangular-block").model_dump(mode="json", by_alias=True)
    graph["source"] = {
        "format": "stl",
        "sha256": blob.sha256,
        "originalFileName": "source.stl",
        "byteSize": blob.byte_size,
        "triangleCount": 0,
        "declaredUnits": "mm",
        "scaleFactor": 1.0,
    }
    graph["features"] = [
        {
            "operation": "importedFaceted",
            "sourceArtifactId": "artifact.source",
            "meshSha256": blob.sha256,
        }
    ]
    project: dict[str, object] = {
        "id": "project.faceted",
        "name": "Faceted",
        "units": "mm",
        "state": {
            "cadgraph": graph,
            "source": {
                "sha256": blob.sha256,
                "format": "stl",
                "originalFileName": "source.stl",
                "declaredUnits": "mm",
                "scaleFactor": 1.0,
            },
            "currentVersionId": "version.faceted.1",
        },
    }

    payload = _operation_payload(project, "rebuild", OperationRequest(), store)
    assert payload["sourcePath"] == str(store.path_for(blob.sha256))

    graph["source"]["sha256"] = "f" * 64
    with pytest.raises(APIError, match="provenance") as graph_error:
        _operation_payload(project, "rebuild", OperationRequest(), store)
    assert graph_error.value.code == "faceted_graph_source_mismatch"
    graph["source"]["sha256"] = blob.sha256

    graph["features"][0]["meshSha256"] = "f" * 64
    with pytest.raises(APIError, match="does not match") as error:
        _operation_payload(project, "rebuild", OperationRequest(), store)
    assert error.value.code == "faceted_source_mismatch"


def test_analyzed_freeform_source_is_preflighted_but_faceted_mode_remains_available(
    tmp_path: Path,
) -> None:
    store = LocalCAS(tmp_path / "storage")
    blob = store.put_bytes(b"solid source\nendsolid source\n")
    project: dict[str, object] = {
        "id": "project.freeform",
        "name": "Freeform",
        "units": "mm",
        "state": {
            "cadgraph": None,
            "source": {
                "sha256": blob.sha256,
                "format": "stl",
                "originalFileName": "source.stl",
                "declaredUnits": "mm",
                "scaleFactor": 1.0,
            },
            "patches": [
                {"id": "patch.overridden", "type": "plane", "areaMm2": 100.0},
            ],
            "analysis": {
                "settings": {
                    "smoothAngleDeg": 12.0,
                    "planarFitToleranceMm": 0.005,
                    "cylinderFitToleranceMm": 0.01,
                    "minimumCylinderCoverageDeg": 300.0,
                    "maximumCylinderAxisNormalComponent": 0.05,
                    "minimumPatchAreaMm2": 1e-8,
                    "stableIdResolutionMm": 1e-5,
                },
                "patches": [
                    {"id": "patch.freeform", "type": "freeform", "areaMm2": 99.0},
                    {"id": "patch.plane", "type": "plane", "areaMm2": 1.0},
                ],
            },
        },
    }

    # Freeform patches no longer pre-block the automatic path: the
    # reconstruct job's candidate evaluation decides and fails closed.
    freeform_payload = _operation_payload(project, "reconstruct", OperationRequest(), store)
    assert freeform_payload["settings"] == {}

    payload = _operation_payload(
        project,
        "reconstruct",
        OperationRequest(settings={"mode": "faceted", "sewingTolerance": 0.05}),
        store,
    )
    assert payload["settings"] == {"mode": "faceted", "sewingTolerance": 0.05}

    inch_project = {**project, "units": "in"}
    with pytest.raises(APIError) as transform_error:
        _operation_payload(
            inch_project,
            "reconstruct",
            OperationRequest(settings={"mode": "faceted", "sewingTolerance": 0.05}),
            store,
        )
    assert transform_error.value.code == "faceted_source_transform_unsupported"
    mm_repair = _operation_payload(project, "repair", OperationRequest(), store)
    inch_repair = _operation_payload(inch_project, "repair", OperationRequest(), store)
    assert mm_repair["inputHash"] != inch_repair["inputHash"]


def test_analyzed_filleted_extrusion_can_enter_bounded_line_arc_solver(tmp_path: Path) -> None:
    store = LocalCAS(tmp_path / "storage")
    blob = store.put_bytes(b"solid source\nendsolid source\n")
    analysis_settings = {
        "smoothAngleDeg": 12.0,
        "planarFitToleranceMm": 0.005,
        "cylinderFitToleranceMm": 0.01,
        "minimumCylinderCoverageDeg": 300.0,
        "maximumCylinderAxisNormalComponent": 0.05,
        "minimumPatchAreaMm2": 1e-8,
        "stableIdResolutionMm": 1e-5,
    }
    patches = [
        {"id": "patch.curved-sides", "type": "freeform", "areaMm2": 15_062.0},
        {
            "id": "patch.top",
            "type": "plane",
            "areaMm2": 604.476,
            "fit": {"normal": [0.0, 0.0, 1.0]},
        },
        {
            "id": "patch.bottom",
            "type": "plane",
            "areaMm2": 604.476,
            "fit": {"normal": [0.0, 0.0, -1.0]},
        },
    ]
    project: dict[str, object] = {
        "id": "project.filleted-extrusion",
        "name": "Filleted extrusion",
        "units": "mm",
        "state": {
            "cadgraph": None,
            "source": {
                "sha256": blob.sha256,
                "format": "stl",
                "originalFileName": "stand.stl",
                "declaredUnits": "mm",
                "scaleFactor": 1.0,
            },
            "analysis": {"settings": analysis_settings, "patches": patches},
            "patches": patches,
        },
    }

    payload = _operation_payload(project, "reconstruct", OperationRequest(), store)
    assert payload["settings"] == {}

    state = project["state"]
    assert isinstance(state, dict)
    analysis = state["analysis"]
    assert isinstance(analysis, dict)
    # A rejected analysis-time prismatic candidate no longer pre-blocks the
    # queue: the reconstruct job's own candidate evaluation is the authority.
    analysis["prismaticCandidate"] = {"accepted": False, "profiles": []}
    assert _operation_payload(project, "reconstruct", OperationRequest(), store)["settings"] == {}

    analysis["prismaticCandidate"] = {
        "accepted": True,
        "profiles": [[{"kind": "arc"}, {"kind": "line"}]],
    }
    assert _operation_payload(project, "reconstruct", OperationRequest(), store)["settings"] == {}


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
