from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import trimesh
from mesh2param.curved_fixtures import (
    CURVED_FIXTURES_BY_SLUG,
    FIXTURE_STL_NAME,
    generate_curved_fixture,
)
from mesh2param.curved_patch import (
    CurvedNetworkSettings,
    CurvedPatchError,
    CurvedPatchSettings,
    reconstruct_plate_network,
)
from mesh2param.segmentation import segment_mesh
from mesh2param_api.jobs.handlers import JobFailure, run_handler

SETTINGS = CurvedPatchSettings(
    fit_tolerance_mm=0.25,
    surface_deviation_tolerance_mm=0.3,
    comparison_sample_count=300,
)


@pytest.fixture(scope="module")
def bump_plate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("bump-plate-overrides")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-bump-plate"], root)
    return root / "bspline-bump-plate" / FIXTURE_STL_NAME


def _mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(path, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


def _freeform_id(mesh: trimesh.Trimesh) -> str:
    return next(patch.id for patch in segment_mesh(mesh).patches if patch.kind == "freeform")


@pytest.mark.geometry
def test_locked_freeform_refuses_splitting(bump_plate: Path) -> None:
    mesh = _mesh(bump_plate)
    with pytest.raises(CurvedPatchError) as excinfo:
        reconstruct_plate_network(
            mesh,
            settings=SETTINGS,
            network_settings=CurvedNetworkSettings(force_split=True),
            patch_overrides={_freeform_id(mesh): {"locked": True}},
        )
    assert excinfo.value.code == "curved_patch_locked_split"


@pytest.mark.geometry
def test_locked_freeform_still_reconstructs_single_patch(bump_plate: Path) -> None:
    mesh = _mesh(bump_plate)
    result = reconstruct_plate_network(
        mesh, settings=SETTINGS, patch_overrides={_freeform_id(mesh): {"locked": True}}
    )
    assert len(result.network.patches) == 1


@pytest.mark.geometry
def test_overrides_fail_closed(bump_plate: Path) -> None:
    mesh = _mesh(bump_plate)
    freeform = _freeform_id(mesh)

    with pytest.raises(CurvedPatchError) as unknown:
        reconstruct_plate_network(
            mesh, settings=SETTINGS, patch_overrides={"patch.missing": {"locked": True}}
        )
    assert unknown.value.code == "curved_patch_override_unknown"

    with pytest.raises(CurvedPatchError) as invalid:
        reconstruct_plate_network(
            mesh, settings=SETTINGS, patch_overrides={freeform: {"kind": "banana"}}
        )
    assert invalid.value.code == "curved_patch_override_rejected"

    # Reclassifying the curved bump as a plane must refit and be rejected:
    # user intent never fabricates geometry.
    with pytest.raises(CurvedPatchError) as refit:
        reconstruct_plate_network(
            mesh, settings=SETTINGS, patch_overrides={freeform: {"kind": "plane"}}
        )
    assert refit.value.code == "curved_patch_override_rejected"


def _progress(_phase: str, _value: float, _detail: str | None) -> None:
    return None


@pytest.mark.geometry
def test_handler_applies_persisted_patch_edits(bump_plate: Path, tmp_path: Path) -> None:
    mesh = _mesh(bump_plate)
    freeform = _freeform_id(mesh)
    payload = {
        "sourcePath": str(bump_plate),
        "units": "mm",
        "settings": {"mode": "curved", "fitTolerance": 0.25, "surfaceDeviationTolerance": 0.3},
        "source": {
            "format": "stl",
            "sha256": hashlib.sha256(bump_plate.read_bytes()).hexdigest(),
            "originalFileName": bump_plate.name,
            "declaredUnits": "mm",
            "scaleFactor": 1.0,
        },
        "projectState": {
            "patches": [{"id": freeform, "type": "freeform", "locked": True}],
            "settings": {},
        },
    }
    output = run_handler("reconstruct", payload, tmp_path, _progress)
    settings_state = output.state_patch["settings"]["curvedReconstruction"]
    assert settings_state["appliedPatchOverrides"] == [freeform]

    # The same locked patch blocks a forced split through the job settings.
    payload["settings"] = {"mode": "curved", "forceSplit": True}
    with pytest.raises(JobFailure) as excinfo:
        run_handler("reconstruct", payload, tmp_path / "split", _progress)
    assert excinfo.value.code == "curved_patch_locked_split"
