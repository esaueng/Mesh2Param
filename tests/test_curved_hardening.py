from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

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
    ReconstructionBudget,
    reconstruct_plate_network,
)
from mesh2param.fit_cache import CurvedFitCache, mesh_content_sha256
from mesh2param.step_audit import StepAuditError, audit_step_file
from mesh2param.validation import export_step_validated

# scripts/ is not a package; a sys.path entry keeps the module importable by
# name so ProcessPoolExecutor children can unpickle its functions.
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[1] / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from run_curved_baseline import run_baseline  # type: ignore[import-not-found]  # noqa: E402

SETTINGS = CurvedPatchSettings(
    fit_tolerance_mm=0.25,
    surface_deviation_tolerance_mm=0.3,
    comparison_sample_count=500,
)


@pytest.fixture(scope="module")
def bump_plate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("bump-plate-hardening")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-bump-plate"], root)
    return root / "bspline-bump-plate"


def _load(directory: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(directory / FIXTURE_STL_NAME, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


@pytest.mark.geometry
def test_progress_reports_every_stage_in_order(bump_plate: Path) -> None:
    mesh = _load(bump_plate)
    stages: list[tuple[str, float]] = []
    reconstruct_plate_network(
        mesh, settings=SETTINGS, progress=lambda phase, fraction: stages.append((phase, fraction))
    )
    phases = [phase for phase, _ in stages]
    assert phases == [
        "segmenting mesh",
        "parameterizing chart",
        "fitting surface",
        "assembling solid",
        "validating solid",
        "finished",
    ]
    fractions = [fraction for _, fraction in stages]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 100.0


@pytest.mark.geometry
def test_cancellation_fails_closed(bump_plate: Path) -> None:
    mesh = _load(bump_plate)
    with pytest.raises(CurvedPatchError) as excinfo:
        reconstruct_plate_network(mesh, settings=SETTINGS, should_cancel=lambda: True)
    assert excinfo.value.code == "curved_patch_cancelled"


@pytest.mark.geometry
def test_wall_clock_budget_fails_closed(bump_plate: Path) -> None:
    mesh = _load(bump_plate)
    settings = CurvedPatchSettings(
        fit_tolerance_mm=0.25,
        surface_deviation_tolerance_mm=0.3,
        budget=ReconstructionBudget(wall_clock_seconds=1e-3),
    )
    with pytest.raises(CurvedPatchError) as excinfo:
        reconstruct_plate_network(mesh, settings=settings)
    assert excinfo.value.code == "curved_patch_time_budget"


@pytest.mark.geometry
def test_patch_budget_blocks_splitting(bump_plate: Path) -> None:
    mesh = _load(bump_plate)
    settings = CurvedPatchSettings(
        fit_tolerance_mm=0.25,
        surface_deviation_tolerance_mm=0.3,
        comparison_sample_count=300,
        budget=ReconstructionBudget(maximum_patches=1),
    )
    with pytest.raises(CurvedPatchError) as excinfo:
        reconstruct_plate_network(
            mesh, settings=settings, network_settings=CurvedNetworkSettings(force_split=True)
        )
    assert excinfo.value.code == "curved_patch_patch_budget"


@pytest.mark.geometry
def test_control_point_budget_clamps_refinement(bump_plate: Path) -> None:
    mesh = _load(bump_plate)
    settings = CurvedPatchSettings(
        fit_tolerance_mm=0.25,
        surface_deviation_tolerance_mm=0.3,
        comparison_sample_count=300,
        budget=ReconstructionBudget(maximum_total_control_points=100),
    )
    result = reconstruct_plate_network(mesh, settings=settings)
    (candidate,) = result.candidates
    assert candidate["controlPoints"] <= 100


@pytest.mark.geometry
def test_fit_cache_hits_and_reproduces_the_result(bump_plate: Path, tmp_path: Path) -> None:
    mesh = _load(bump_plate)
    cache = CurvedFitCache(tmp_path / "cache")
    first = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert first.cache_status == "stored"
    assert list((tmp_path / "cache").glob("*.json"))

    second = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert second.cache_status == "hit"
    assert second.artifact_sha256 == first.artifact_sha256
    assert second.face_surfaces == first.face_surfaces

    shas = []
    for run, result in (("a", first), ("b", second)):
        report = export_step_validated(result.solid, tmp_path / run / "cached.step")
        shas.append(report.sha256)
    assert shas[0] == shas[1]


def test_cache_key_tracks_settings_and_source(bump_plate: Path) -> None:
    mesh = _load(bump_plate)
    cache = CurvedFitCache(Path("unused"))
    sha = mesh_content_sha256(mesh)
    charts = (mesh.vertices, mesh.faces)
    base = cache.key(sha, SETTINGS, CurvedNetworkSettings(), charts)
    assert base == cache.key(sha, SETTINGS, CurvedNetworkSettings(), charts)
    looser = CurvedPatchSettings(fit_tolerance_mm=0.5, surface_deviation_tolerance_mm=0.3)
    assert base != cache.key(sha, looser, CurvedNetworkSettings(), charts)
    assert base != cache.key(sha[::-1], SETTINGS, CurvedNetworkSettings(), charts)


@pytest.mark.geometry
def test_step_audit_confirms_reconstructed_inventory(bump_plate: Path, tmp_path: Path) -> None:
    mesh = _load(bump_plate)
    result = reconstruct_plate_network(mesh, settings=SETTINGS)
    export_step_validated(result.solid, tmp_path / "audited.step")
    audit = audit_step_file(tmp_path / "audited.step")
    assert audit.valid
    assert audit.solid_count == 1
    assert audit.surface_counts["bspline"] == 1
    assert audit.surface_counts["plane"] == 5
    assert audit.advanced_face_count == 6


def test_step_audit_rejects_structural_defects(tmp_path: Path) -> None:
    broken = tmp_path / "broken.step"
    broken.write_text("not a step file", encoding="utf-8")
    with pytest.raises(StepAuditError):
        audit_step_file(broken)

    dangling = tmp_path / "dangling.step"
    dangling.write_text(
        "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
        "#1=MANIFOLD_SOLID_BREP('',#2);\n"
        "ENDSEC;\nEND-ISO-10303-21;\n",
        encoding="utf-8",
    )
    audit = audit_step_file(dangling)
    assert not audit.valid
    assert any("missing #2" in error for error in audit.errors)
    assert any("closed shells" in error for error in audit.errors)


@pytest.mark.geometry
def test_parallel_baseline_reduction_is_deterministic(tmp_path: Path) -> None:
    fixtures_root = tmp_path / "fixtures"
    generated = [
        generate_curved_fixture(CURVED_FIXTURES_BY_SLUG[slug], fixtures_root)
        for slug in ("non-manifold-fin", "multi-body-boxes")
    ]
    manifest = {"fixtures": [fixture.to_dict() for fixture in generated]}
    (fixtures_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    serial = run_baseline(fixtures_root, tmp_path / "serial.json", 100, workers=1)
    parallel = run_baseline(fixtures_root, tmp_path / "parallel.json", 100, workers=2)

    def stripped(baseline: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for row in baseline["fixtures"]:
            row = dict(row)
            row.pop("runtimeSeconds", None)
            rows.append(row)
        return rows

    assert stripped(serial) == stripped(parallel)
