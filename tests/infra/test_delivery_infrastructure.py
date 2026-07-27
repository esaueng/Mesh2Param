# ruff: noqa: E402
from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.check_samples import compare_sample_trees, fingerprint_tree
from scripts.verify_container_security import (
    validate_compose_model,
    validate_inspect_documents,
)

# `pnpm test` and `pnpm test:frontend` fan out to per-package runs in CI, and
# `pnpm test:geometry` runs inside the full backend pytest invocation, so those
# names never appear verbatim in the workflow.
_VERIFY_STEP_EQUIVALENTS = {
    "pnpm test": (("vitest", "run"), ("pytest",)),
    "pnpm test:geometry": (("pytest",),),
}


def _workflow_commands(workflow: str) -> tuple[tuple[str, ...], ...]:
    document = yaml.safe_load(workflow)
    if not isinstance(document, dict) or not isinstance(document.get("jobs"), dict):
        return ()
    commands: list[tuple[str, ...]] = []
    for job in document["jobs"].values():
        if not isinstance(job, dict) or not isinstance(job.get("steps"), list):
            continue
        for step in job["steps"]:
            if not isinstance(step, dict) or not isinstance(step.get("run"), str):
                continue
            continued = ""
            for raw_line in step["run"].splitlines():
                line = (continued + raw_line.strip()).strip()
                if line.endswith("\\"):
                    continued = line[:-1] + " "
                    continue
                continued = ""
                tokens = tuple(shlex.split(line, comments=True))
                if tokens:
                    commands.append(tokens)
            if continued.strip():
                commands.append(tuple(shlex.split(continued, comments=True)))
    return tuple(commands)


def _contains_token_sequence(command: tuple[str, ...], marker: tuple[str, ...]) -> bool:
    return any(
        command[index : index + len(marker)] == marker
        for index in range(len(command) - len(marker) + 1)
    )


def _workflow_covers(workflow: str, step: str) -> bool:
    """Whether the CI workflow runs `step`, directly or through an equivalent."""
    commands = _workflow_commands(workflow)
    expected = tuple(shlex.split(step))
    if expected in commands:
        return True
    equivalents = _VERIFY_STEP_EQUIVALENTS.get(step)
    # No exact command and no declared equivalent means the step is not covered;
    # `all(())` would otherwise report an unknown step as covered.
    if not equivalents:
        return False
    return all(
        any(_contains_token_sequence(command, marker) for command in commands)
        for marker in equivalents
    )


def test_workflow_coverage_does_not_accept_command_prefix_collisions() -> None:
    collisions = """
jobs:
  quality:
    steps:
      - run: |
          pnpm build:packages
          pnpm test:e2e
"""
    assert _workflow_covers(collisions, "pnpm build:packages")
    assert _workflow_covers(collisions, "pnpm test:e2e")
    assert not _workflow_covers(collisions, "pnpm build")
    assert not _workflow_covers(collisions, "pnpm test")


def _inspect_document(service: str) -> dict[str, object]:
    backend = service in {"api", "worker"}
    return {
        "Id": f"{service}-container",
        "Config": {"User": "10001:10001" if backend else "101:101"},
        "HostConfig": {
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "NanoCpus": 250_000_000,
            "Memory": 128 * 1024 * 1024,
            "PidsLimit": 64,
            "NetworkMode": "none" if service == "worker" else "mesh2param_backend",
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=32m"},
        },
        "State": {"Running": True, "Health": {"Status": "healthy"}},
        "Mounts": (
            [
                {
                    "Type": "volume",
                    "Destination": "/var/lib/mesh2param",
                    "RW": True,
                }
            ]
            if backend
            else []
        ),
        "NetworkSettings": {
            "Ports": (
                {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8080"}]}
                if service == "web"
                else {"8000/tcp": None} if service == "api" else {}
            )
        },
    }


def test_sample_tree_comparison_detects_missing_extra_and_changed_files(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected"
    actual = tmp_path / "actual"
    expected.mkdir()
    actual.mkdir()
    (expected / "same.txt").write_bytes(b"same")
    (actual / "same.txt").write_bytes(b"same")
    assert compare_sample_trees(expected, actual).matches

    (expected / "changed.txt").write_bytes(b"expected")
    (actual / "changed.txt").write_bytes(b"actual")
    (expected / "missing.txt").write_bytes(b"missing")
    (actual / "unexpected.txt").write_bytes(b"unexpected")
    comparison = compare_sample_trees(expected, actual)

    assert comparison.changed == ("changed.txt",)
    assert comparison.missing == ("missing.txt",)
    assert comparison.unexpected == ("unexpected.txt",)
    assert not comparison.matches


def test_sample_inventory_rejects_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "samples"
    root.mkdir()
    target = root / "target.txt"
    target.write_text("sample", encoding="utf-8")
    (root / "link.txt").symlink_to(target)

    with pytest.raises(ValueError, match="symlinks"):
        fingerprint_tree(root)


def test_effective_container_inspection_contract() -> None:
    documents = {service: _inspect_document(service) for service in ("api", "worker", "web")}
    results = validate_inspect_documents(documents)
    assert results
    assert all(result.passed for result in results)

    api_config = documents["api"]["Config"]
    assert isinstance(api_config, dict)
    api_config["User"] = "0:0"
    failed = validate_inspect_documents(documents)
    assert any(result.name == "inspect.api.non-root" and not result.passed for result in failed)


def test_resolved_compose_model_contract() -> None:
    model: dict[str, object] = {
        "services": {
            "api": {"ports": [], "read_only": True, "user": "10001:10001"},
            "worker": {
                "ports": [],
                "read_only": True,
                "user": "10001:10001",
                "network_mode": "none",
            },
            "web": {"ports": [{"published": 8080}], "read_only": True, "user": "101:101"},
        },
        "networks": {"backend": {"internal": True}, "edge": {}},
    }
    results = validate_compose_model(model)
    assert all(result.passed for result in results)


def test_delivery_files_pin_images_and_security_controls() -> None:
    backend = (REPOSITORY_ROOT / "infra/backend.Dockerfile").read_text(encoding="utf-8")
    web = (REPOSITORY_ROOT / "infra/web.Dockerfile").read_text(encoding="utf-8")
    dockerignore = (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8")
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    nginx = (REPOSITORY_ROOT / "infra/nginx/nginx.conf.template").read_text(
        encoding="utf-8"
    )
    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7" in backend
    assert "sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa" in backend
    assert "ARG BACKEND_PLATFORM=linux/amd64" in backend
    assert backend.count("FROM --platform=${BACKEND_PLATFORM}") == 2
    assert "--reinstall-package mesh2param" in backend
    assert "--reinstall-package mesh2param-contracts" in backend
    assert "RUN /opt/venv/bin/python -P - <<'PY'" in backend
    assert "BRepCheck_Analyzer(restored.val().wrapped).IsValid()" in backend
    assert "sha256:dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94" in web
    assert "sha256:42a7d7f2ee23e9f5a1dcdf3647ba5c585bbd18f79e79cd817e70e8cd61c55779" in web
    assert "!packages/contracts/tests/fixtures/base.cadgraph.json" in dockerignore
    assert compose.count("read_only: true") == 3
    assert compose.count('cap_drop: ["ALL"]') == 3
    assert compose.count("platform: linux/amd64") == 2
    assert "network_mode: none" in compose
    assert '127.0.0.1:${COMPOSE_WEB_PORT:-8080}:8080' in compose
    assert "urllib.parse.urlsplit(os.environ['MESH2PARAM_PUBLIC_URL']).netloc" in compose
    assert 'wget -qO- --header="Host: $${host}"' in compose
    assert "proxy_request_buffering off" in nginx
    assert "proxy_buffering off" in nginx
    assert "Content-Security-Policy" in nginx
    assert "location = /docs" in nginx
    assert "location = /openapi.json" in nginx
    docs_location = nginx.split("location = /docs", 1)[1].split(
        "location = /index.html", 1
    )[0]
    assert "'unsafe-inline'" not in docs_location
    assert "default-src 'none'" in docs_location

    action_references = re.findall(r"uses:\s+[^@\s]+@([^\s#]+)", workflow)
    assert action_references
    assert all(re.fullmatch(r"[0-9a-f]{40}", reference) for reference in action_references)
    # The workflow runs the repository's verification in a parallel matrix rather
    # than as one `pnpm verify` invocation, so assert the coverage that script
    # defines instead of the literal call. Reading the definition keeps this
    # honest: adding a step to `verify` without wiring it into CI now fails here.
    verify_script = json.loads((REPOSITORY_ROOT / "package.json").read_text())["scripts"]["verify"]
    verify_steps = [step.strip() for step in verify_script.split("&&")]
    assert verify_steps
    uncovered = [step for step in verify_steps if not _workflow_covers(workflow, step)]
    assert not uncovered, f"CI does not run these `pnpm verify` steps: {uncovered}"
    assert "pnpm cf:check" in workflow
    assert "verify_container_security.py" in workflow
