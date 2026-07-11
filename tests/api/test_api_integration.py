from __future__ import annotations

import io
import json
import struct
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from mesh2param_api import Settings, create_app


def binary_triangle_stl() -> bytes:
    triangle = struct.pack(
        "<12fH",
        0,
        0,
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        1,
        0,
        0,
    )
    return b"Mesh2Param test".ljust(80, b"\0") + struct.pack("<I", 1) + triangle


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(  # type: ignore[call-arg]
        environment="test",
        data_dir=tmp_path,
        worker_count=1,
        job_timeout_seconds=120,
        worker_poll_seconds=0.02,
        worker_cancel_grace_seconds=0.1,
        sse_poll_seconds=0.02,
        sse_keepalive_seconds=1,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as active:
        yield active


def wait_job(client: TestClient, job_id: str, timeout: float = 180) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        last = response.json()["data"]
        if last["status"] in {"completed", "failed", "cancelled"}:
            return last
        time.sleep(0.03)
    raise AssertionError(f"job did not terminate: {last}")


def create_project(
    client: TestClient, name: str = "API project"
) -> tuple[dict[str, Any], str]:
    response = client.post("/api/projects", json={"name": name, "units": "mm"})
    assert response.status_code == 201, response.text
    return response.json()["data"], response.headers["etag"]


def current_project(client: TestClient, project_id: str) -> tuple[dict[str, Any], str]:
    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200, response.text
    return response.json()["data"], response.headers["etag"]


def test_health_projects_upload_diagnostics_reopen_and_delete(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    schema = openapi.json()
    assert schema["info"]["title"] == "Mesh2Param API"
    upload_schema = schema["paths"]["/api/projects/{project_id}/upload"]["post"]
    assert (
        upload_schema["requestBody"]["content"]["application/octet-stream"]["schema"]
        == {"type": "string", "format": "binary"}
    )
    representative_responses = (
        schema["paths"]["/api/projects/{project_id}"]["get"]["responses"]["200"],
        schema["paths"]["/api/jobs/{job_id}"]["get"]["responses"]["200"],
        schema["paths"]["/api/projects/{project_id}/artifacts"]["get"]["responses"]["200"],
        schema["paths"]["/api/projects/{project_id}/versions"]["get"]["responses"]["200"],
        schema["paths"]["/api/projects/{project_id}/patches"]["get"]["responses"]["200"],
    )
    assert all(
        response["content"]["application/json"]["schema"].get("$ref")
        for response in representative_responses
    )
    docs = client.get("/docs")
    assert docs.status_code == 200 and "Mesh2Param API" in docs.text
    missing_sample = client.post("/api/samples/not-a-sample/open")
    assert missing_sample.status_code == 404
    assert missing_sample.json()["error"]["code"] == "sample_not_found"

    project, etag = create_project(client)
    project_id = project["id"]
    assert client.get("/api/projects").json()["data"]["total"] == 1
    stale = client.patch(
        f"/api/projects/{project_id}",
        json={"name": "stale"},
        headers={"If-Match": '"rev-0"'},
    )
    assert stale.status_code == 412
    assert stale.json()["error"]["code"] == "project_revision_conflict"

    upload = client.post(
        f"/api/projects/{project_id}/upload",
        params={
            "filename": "triangle.stl",
            "units": "mm",
            "unitsConfirmed": "true",
            "scaleFactor": "1",
        },
        headers={"If-Match": etag, "Content-Type": "application/octet-stream"},
        content=binary_triangle_stl(),
    )
    assert upload.status_code == 202, upload.text
    upload_job = wait_job(client, upload.json()["data"]["job"]["id"])
    assert upload_job["status"] == "completed", upload_job
    reopened, etag = current_project(client, project_id)
    assert reopened["state"]["source"]["sha256"]
    assert reopened["state"]["diagnostics"]["triangleCount"] == 1

    events = client.get(f"/api/jobs/{upload_job['id']}/events")
    assert events.status_code == 200
    assert "event: completed" in events.text
    assert "event: progress" in events.text

    delete = client.delete(
        f"/api/projects/{project_id}", headers={"If-Match": etag}
    )
    assert delete.status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_worker_timeout_crash_retry_and_running_cancel(client: TestClient) -> None:
    project, _ = create_project(client, "Worker lifecycle")
    project_id = project["id"]
    repo = cast(Any, client.app).state.repository

    timed_out = repo.create_job(
        project_id,
        project["revision"],
        "test_hang",
        {"inputHash": "c" * 64, "settings": {}},
        timeout_seconds=0.15,
        max_attempts=1,
    )
    health_started = time.monotonic()
    assert client.get("/health").status_code == 200
    assert time.monotonic() - health_started < 0.5
    timeout_result = wait_job(client, timed_out["id"])
    assert timeout_result["status"] == "failed"
    assert timeout_result["error"]["code"] == "worker_timeout"
    assert timeout_result["progress"] < 100

    project, _ = current_project(client, project_id)
    crashed = repo.create_job(
        project_id,
        project["revision"],
        "test_crash",
        {"inputHash": "d" * 64, "settings": {}},
        timeout_seconds=10,
        max_attempts=2,
    )
    crash_result = wait_job(client, crashed["id"])
    assert crash_result["status"] == "failed"
    assert crash_result["error"]["code"] == "worker_crash"
    assert crash_result["attempt"] == 2
    events, terminal = repo.events_after(crashed["id"], 0)
    assert terminal and any(event["event"] == "retry_scheduled" for event in events)

    project, _ = current_project(client, project_id)
    running = repo.create_job(
        project_id,
        project["revision"],
        "test_hang",
        {"inputHash": "e" * 64, "settings": {}},
        timeout_seconds=30,
        max_attempts=1,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if client.get(f"/api/jobs/{running['id']}").json()["data"]["status"] == "running":
            break
        time.sleep(0.02)
    cancellation = client.post(f"/api/jobs/{running['id']}/cancel")
    assert cancellation.status_code == 202
    cancelled = wait_job(client, running["id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["progress"] < 100


@pytest.mark.geometry
def test_sample_reconstruct_rebuild_validate_export_versions_and_cancel(
    client: TestClient,
) -> None:
    opened = client.post("/api/samples/l-bracket-with-holes/open")
    assert opened.status_code == 202, opened.text
    project_id = opened.json()["data"]["project"]["id"]
    sample_job = wait_job(client, opened.json()["data"]["job"]["id"])
    assert sample_job["status"] == "completed", sample_job

    project, etag = current_project(client, project_id)
    assert project["state"]["source"]["originalFileName"] == "source-random.stl"
    assert project["state"]["cadgraph"]

    repair = client.post(
        f"/api/projects/{project_id}/repair",
        headers={"If-Match": etag},
        json={},
    )
    assert repair.status_code == 202, repair.text
    repaired = wait_job(client, repair.json()["data"]["id"])
    assert repaired["status"] == "completed", repaired
    project, etag = current_project(client, project_id)
    assert project["state"]["repair"]["operations"]

    analyze = client.post(
        f"/api/projects/{project_id}/analyze",
        headers={"If-Match": etag},
        json={},
    )
    assert analyze.status_code == 202, analyze.text
    analyzed = wait_job(client, analyze.json()["data"]["id"])
    assert analyzed["status"] == "completed", analyzed
    project, etag = current_project(client, project_id)
    assert project["state"]["patches"]
    patch_list = client.get(f"/api/projects/{project_id}/patches")
    assert patch_list.status_code == 200
    patches = patch_list.json()["data"]["items"]
    selected_patch = patches[0]
    patch_update = client.patch(
        f"/api/projects/{project_id}/patches/{selected_patch['id']}",
        headers={"If-Match": etag},
        json={"name": "Locked evidence patch", "locked": True},
    )
    assert patch_update.status_code == 200, patch_update.text
    etag = patch_update.headers["etag"]
    plane = next(item for item in patches if item["type"] == "plane")
    cylinder = next(item for item in patches if item["type"] == "cylinder")
    incompatible_merge = client.post(
        f"/api/projects/{project_id}/patches/merge",
        headers={"If-Match": etag},
        json={"patchIds": [plane["id"], cylinder["id"]]},
    )
    assert incompatible_merge.status_code in {409, 422}
    unchanged = client.get(f"/api/projects/{project_id}/patches").json()["data"]["items"]
    assert len(unchanged) == len(patches)
    assert next(item for item in unchanged if item["id"] == selected_patch["id"])["locked"] is True

    reconstruct = client.post(
        f"/api/projects/{project_id}/reconstruct",
        headers={"If-Match": etag},
        json={},
    )
    assert reconstruct.status_code == 202, reconstruct.text
    reconstructed = wait_job(client, reconstruct.json()["data"]["id"])
    assert reconstructed["status"] == "completed", reconstructed
    project, etag = current_project(client, project_id)
    assert project["state"]["validation"]["stepReimportValid"] is True
    reconstructed_artifacts = {
        item["name"]
        for item in client.get(
            f"/api/projects/{project_id}/artifacts"
        ).json()["data"]["items"]
    }
    assert {
        "model.step",
        "model.cadgraph.json",
        "model.cq.py",
        "source.glb",
        "repaired.glb",
        "analysis-proxy.glb",
        "patches.glb",
        "reconstructed.glb",
        "residual.glb",
        "analysis.json",
        "metrics.json",
        "manifest.json",
    } <= reconstructed_artifacts

    graph_response = client.get(f"/api/projects/{project_id}/cadgraph")
    assert graph_response.status_code == 200
    graph = graph_response.json()["data"]
    patched = client.patch(
        f"/api/projects/{project_id}/cadgraph",
        headers={"If-Match": etag},
        json={"cadgraph": graph},
    )
    assert patched.status_code == 200, patched.text
    etag = patched.headers["etag"]

    for operation in ("rebuild", "validate", "export"):
        response = client.post(
            f"/api/projects/{project_id}/{operation}",
            headers={"If-Match": etag},
            json={},
        )
        assert response.status_code == 202, response.text
        job = wait_job(client, response.json()["data"]["id"])
        assert job["status"] == "completed", job
        _, etag = current_project(client, project_id)

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()["data"]
    names = {item["name"] for item in artifacts["items"]}
    expected_conversion_artifacts = {
        "model.step",
        "model.cadgraph.json",
        "model.cq.py",
        "source.glb",
        "repaired.glb",
        "analysis-proxy.glb",
        "patches.glb",
        "reconstructed.glb",
        "residual.glb",
        "analysis.json",
        "metrics.json",
        "manifest.json",
        "project.mesh2param.json",
        "mesh2param-export.zip",
    }
    assert expected_conversion_artifacts <= names
    step = client.get(f"/api/projects/{project_id}/artifacts/model.step")
    assert step.status_code == 200 and step.content.startswith(b"ISO-10303-21")
    bundle = client.get(f"/api/projects/{project_id}/artifacts/mesh2param-export.zip")
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        bundle_names = set(archive.namelist())
        assert expected_conversion_artifacts - {"mesh2param-export.zip"} <= bundle_names
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["timestamp"]
    assert {
        item["name"] for item in manifest["artifacts"]
    } == bundle_names - {"manifest.json"}

    version_one = client.post(
        f"/api/projects/{project_id}/versions",
        headers={"If-Match": etag},
        json={"label": "Validated"},
    )
    assert version_one.status_code == 201, version_one.text
    etag = version_one.headers["etag"]
    version_two = client.post(
        f"/api/projects/{project_id}/versions",
        headers={"If-Match": etag},
        json={"label": "Exported"},
    )
    assert version_two.status_code == 201, version_two.text
    etag = version_two.headers["etag"]
    restored = client.post(
        f"/api/projects/{project_id}/versions/{version_one.json()['data']['id']}/restore",
        headers={"If-Match": etag},
    )
    assert restored.status_code == 201
    deleted = client.delete(
        f"/api/projects/{project_id}/versions/{version_two.json()['data']['id']}"
    )
    assert deleted.status_code == 204

    project, _ = current_project(client, project_id)
    repo = cast(Any, client.app).state.repository
    hanging = repo.create_job(
        project_id,
        project["revision"],
        "test_hang",
        {"inputHash": "b" * 64, "settings": {}},
        timeout_seconds=30,
    )
    cancellation = client.post(f"/api/jobs/{hanging['id']}/cancel")
    assert cancellation.status_code in {200, 202}
    cancelled = wait_job(client, hanging["id"])
    assert cancelled["status"] == "cancelled"
