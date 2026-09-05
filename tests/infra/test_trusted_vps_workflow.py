from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_trusted_vps_only_executes_protected_main() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/trusted-vps.yml").read_text())
    events = workflow.get("on", workflow.get(True))
    assert events == {"push": {"branches": ["main"]}, "workflow_dispatch": {}}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert set(workflow["jobs"]) == {"packages"}
    job = workflow["jobs"]["packages"]
    assert job["runs-on"] == {"group": "ci-trusted-main", "labels": "ci-small"}
    guard = job["if"]
    assert "github.repository == 'esaueng/Mesh2Param'" in guard
    assert "github.ref == 'refs/heads/main' && github.ref_protected" in guard
    assert "github.event_name == 'push' || github.event_name == 'workflow_dispatch'" in guard
    assert "strategy" not in job
    assert job["timeout-minutes"] == 20
    checkout = next(
        step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"] == {"persist-credentials": False, "ref": "${{ github.sha }}"}
    for step in job["steps"]:
        if "uses" in step:
            assert re.fullmatch(r"[\w/-]+@[0-9a-f]{40}", step["uses"])
            assert step["uses"].split("@")[0] in {
                "actions/checkout",
                "actions/setup-node",
                "actions/upload-artifact",
            }
    text = (ROOT / ".github/workflows/trusted-vps.yml").read_text()
    for forbidden in ("secrets.", "sudo ", "docker prune", "system prune", "rm -rf", "wrangler"):
        assert forbidden not in text
    assert "pnpm install --frozen-lockfile" in text
    assert "ci-vm-1441561" in text
    assert "--maxWorkers=1" in text
    assert "memory.events" in text


def test_existing_hosted_checks_and_deployment_stay_hosted() -> None:
    for filename in ("ci.yml", "cloudflare.yml"):
        workflow = yaml.safe_load((ROOT / ".github/workflows" / filename).read_text())
        for job in workflow["jobs"].values():
            assert job["runs-on"] == "ubuntu-24.04"
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert ci["jobs"]["quality"]["strategy"]["matrix"]["task"] == [
        "static",
        "frontend",
        "backend",
        "browser",
    ]
    assert {"quality", "rust", "containers"} <= ci["jobs"].keys()
