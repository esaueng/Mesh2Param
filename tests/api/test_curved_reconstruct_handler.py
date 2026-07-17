from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from mesh2param.curved_fixtures import (
    CURVED_FIXTURES_BY_SLUG,
    FIXTURE_STL_NAME,
    generate_curved_fixture,
)
from mesh2param_api.jobs.handlers import JobFailure, run_handler


def _progress(_phase: str, _value: float, _detail: str | None) -> None:
    return None


@pytest.fixture(scope="module")
def bump_plate_stl(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("curved-handler")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-bump-plate"], root)
    return root / "bspline-bump-plate" / FIXTURE_STL_NAME


def _payload(source: Path, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "sourcePath": str(source),
        "units": "mm",
        "settings": settings,
        "source": {
            "format": "stl",
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "originalFileName": source.name,
            "declaredUnits": "mm",
            "scaleFactor": 1.0,
        },
    }


@pytest.mark.geometry
def test_curved_reconstruct_emits_the_network_feature(bump_plate_stl: Path, tmp_path: Path) -> None:
    payload = _payload(
        bump_plate_stl,
        {"mode": "curved", "fitTolerance": 0.25, "surfaceDeviationTolerance": 0.3},
    )
    output = run_handler("reconstruct", payload, tmp_path, _progress)

    cadgraph = output.state_patch["cadgraph"]
    assert cadgraph["features"][0]["operation"] == "reconstructedSurfaceNetwork"
    assert (
        cadgraph["features"][0]["artifactSha256"]
        == hashlib.sha256((tmp_path / "curved-plate.json").read_bytes()).hexdigest()
    )
    assert cadgraph["validation"]["status"] == "valid"
    assert cadgraph["validation"]["toleranceSatisfied"] is True

    names = {artifact.name for artifact in output.artifacts}
    assert {
        "curved-plate.json",
        "model.cadgraph.json",
        "model.step",
        "reconstructed.glb",
        "validation.json",
        "curved-reconstruction.json",
    } <= names

    settings_state = output.state_patch["settings"]["curvedReconstruction"]
    assert settings_state["scope"] == "approximate curved B-Rep"
    assert settings_state["approximate"] is True
    assert settings_state["designHistoryRecovered"] is False
    assert settings_state["faceSurfaces"]["bspline"] == 1

    validation = json.loads((tmp_path / "validation.json").read_text(encoding="utf-8"))
    assert validation["stepAudit"]["valid"] is True
    assert validation["curvedReconstruction"]["browserTessellationRepresentsKernelResult"] is True


def test_curved_settings_reject_unsupported_fields(bump_plate_stl: Path, tmp_path: Path) -> None:
    payload = _payload(bump_plate_stl, {"mode": "curved", "unexpected": 1.0})
    with pytest.raises(JobFailure) as excinfo:
        run_handler("reconstruct", payload, tmp_path, _progress)
    assert excinfo.value.code == "invalid_curved_settings"


def test_curved_settings_reject_out_of_bounds_tolerance(
    bump_plate_stl: Path, tmp_path: Path
) -> None:
    payload = _payload(bump_plate_stl, {"mode": "curved", "fitTolerance": 100.0})
    with pytest.raises(JobFailure) as excinfo:
        run_handler("reconstruct", payload, tmp_path, _progress)
    assert excinfo.value.code == "invalid_curved_settings"


@pytest.mark.geometry
def test_curved_reconstruct_fails_closed_on_unsupported_topology(tmp_path: Path) -> None:
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["wavy-slab"], tmp_path)
    source = tmp_path / "wavy-slab" / FIXTURE_STL_NAME
    payload = _payload(source, {"mode": "curved"})
    with pytest.raises(JobFailure) as excinfo:
        run_handler("reconstruct", payload, tmp_path / "job", _progress)
    # The slab's two freeform regions (top and bottom) share no boundary, so
    # the multi-region crease path rejects it with a precise code.
    assert excinfo.value.code == "curved_patch_regions_detached"
    assert "faceted" in (excinfo.value.recommended_action or "")
