"""Guard the self-hosted scheduling policy without executing contributor code."""

import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]


def test_ci_caller_is_immutable_and_passes_no_inputs_or_secrets() -> None:
    caller = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    job = caller["jobs"]["checks"]
    assert re.fullmatch(
        r"esaueng/Mesh2Param/\.github/workflows/fleet-ci\.yml@[0-9a-f]{40}", job["uses"]
    )
    assert set(job) == {"uses", "permissions"}
    assert job["permissions"] == {"contents": "read"}
    assert caller["permissions"] == {"contents": "read"}


def test_only_compatible_jobs_can_use_the_selected_fleet_target() -> None:
    jobs = yaml.safe_load((ROOT / ".github/workflows/fleet-ci.yml").read_text())["jobs"]
    quality = jobs["quality"]
    expression = quality["runs-on"]
    assert "matrix.task" not in expression
    assert "needs" not in quality
    assert quality["strategy"]["matrix"]["task"] == ["static", "frontend", "backend", "browser"]
    assert quality["timeout-minutes"] == 60
    assert jobs["rust"]["runs-on"] == jobs["containers"]["runs-on"] == expression
    for job in jobs.values():
        for step in job.get("steps", []):
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False


def test_fleet_selection_is_opt_in_and_uses_the_shared_slot_label() -> None:
    jobs = yaml.safe_load((ROOT / ".github/workflows/fleet-ci.yml").read_text())["jobs"]
    assert "route" not in jobs
    assert "authorize" not in jobs
    assert all("secrets" not in job for job in jobs.values())
    expression = jobs["quality"]["runs-on"]
    for target in ["ci-server-jane", "ci-server-john"]:
        assert f'"labels":"{target}"' in expression
    assert "ci-small" not in expression
    assert "ci-server-jane-1" not in expression
    assert "ci-server-jane-2" not in expression
    assert expression.endswith("|| '\"ubuntu-24.04\"') }}")


def test_python_bootstrap_uses_the_project_pin_without_an_ubuntu_catalog() -> None:
    jobs = yaml.safe_load((ROOT / ".github/workflows/fleet-ci.yml").read_text())["jobs"]
    steps = jobs["quality"]["steps"]
    assert not any(step.get("uses", "").startswith("actions/setup-python@") for step in steps)
    setup = next(
        i for i, step in enumerate(steps) if step.get("uses", "").startswith("astral-sh/setup-uv@")
    )
    install = next(i for i, step in enumerate(steps) if "uv python install" in step.get("run", ""))
    assert setup < install
    script = steps[install]["run"]
    assert ".python-version" in script
    assert "--managed-python" in script
    assert "GITHUB_PATH" in script
    assert "3.12.11" not in script
