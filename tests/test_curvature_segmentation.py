"""G1 principal-curvature estimation and opt-in smooth-region subdivision."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import trimesh
from mesh2param.segmentation import (
    SegmentationSettings,
    estimate_principal_curvatures,
    segment_mesh,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SPANNER_ROOT = REPOSITORY_ROOT / "samples" / "general-parametric-benchmark" / "spanner-filleted"


def _spanner_mesh() -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(SPANNER_ROOT / "source.stl", process=True)
    assert isinstance(mesh, trimesh.Trimesh)
    return mesh


def _spanner_manifest() -> dict[str, Any]:
    payload = json.loads((SPANNER_ROOT / "fixture.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _open_cylinder(radius_mm: float = 5.0) -> trimesh.Trimesh:
    ring_count = 9
    side_count = 64
    vertices = np.asarray(
        [
            (
                radius_mm * np.cos(2.0 * np.pi * side / side_count),
                radius_mm * np.sin(2.0 * np.pi * side / side_count),
                float(ring),
            )
            for ring in range(ring_count)
            for side in range(side_count)
        ],
        dtype=np.float64,
    )
    faces: list[tuple[int, int, int]] = []
    for ring in range(ring_count - 1):
        for side in range(side_count):
            following = (side + 1) % side_count
            lower = ring * side_count + side
            lower_following = ring * side_count + following
            upper = (ring + 1) * side_count + side
            upper_following = (ring + 1) * side_count + following
            faces.append((lower, lower_following, upper_following))
            faces.append((lower, upper_following, upper))
    return trimesh.Trimesh(
        vertices=vertices,
        faces=np.asarray(faces, dtype=np.int64),
        process=False,
    )


@pytest.mark.geometry
def test_robust_quadric_principal_curvature_is_deterministic_on_a_cylinder() -> None:
    mesh = _open_cylinder()
    settings = SegmentationSettings(enable_curvature_subsegmentation=True)
    face_ids = tuple(range(len(mesh.faces)))

    first = estimate_principal_curvatures(mesh, face_ids, settings)
    repeated = estimate_principal_curvatures(mesh, tuple(reversed(face_ids)), settings)

    assert first == repeated
    side_count = 64
    interior = [
        estimate
        for estimate in first
        if estimate.valid and 2 * side_count <= estimate.vertex_id < 7 * side_count
    ]
    assert len(interior) == 5 * side_count
    minimum = float(np.median([abs(estimate.minimum_mm_inv) for estimate in interior]))
    maximum = float(np.median([abs(estimate.maximum_mm_inv) for estimate in interior]))
    assert minimum < 5e-4
    assert maximum == pytest.approx(1.0 / 5.0, rel=0.02)


@pytest.mark.geometry
@pytest.mark.samples
def test_curvature_stage_is_off_by_default_and_preserves_serialization() -> None:
    mesh = _spanner_mesh()

    default = segment_mesh(mesh)
    explicit_off = segment_mesh(
        mesh,
        SegmentationSettings(enable_curvature_subsegmentation=False),
    )

    assert default.to_dict() == explicit_off.to_dict()
    assert default.counts_by_type["freeform"] == 1
    serialized = default.to_dict()
    assert "countsByCurvatureClass" not in serialized
    assert "curvatureSubsegmentation" not in serialized["settings"]
    assert all("curvatureEvidence" not in patch for patch in serialized["patches"])


@pytest.mark.geometry
def test_under_resolved_curvature_evidence_remains_strict_json() -> None:
    mesh = trimesh.Trimesh(
        vertices=np.asarray(
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (1.0, 1.0, 0.2),
                (0.5, 0.5, 1.0),
            ],
            dtype=np.float64,
        ),
        faces=np.asarray(
            [
                (0, 1, 4),
                (1, 3, 4),
                (3, 2, 4),
                (2, 0, 4),
                (0, 2, 3),
                (0, 3, 1),
            ],
            dtype=np.int64,
        ),
        process=False,
    )
    settings = SegmentationSettings(
        smooth_angle_deg=89.0,
        planar_fit_tolerance_mm=1e-12,
        cylinder_fit_tolerance_mm=1e-12,
        sphere_fit_tolerance_mm=1e-12,
        cone_fit_tolerance_mm=1e-12,
        torus_fit_tolerance_mm=1e-12,
        enable_curvature_subsegmentation=True,
    )

    serialized = segment_mesh(mesh, settings).to_dict()

    assert any(
        patch["curvatureEvidence"]["fitRmsP95Mm"] is None
        for patch in serialized["patches"]
    )
    json.dumps(serialized, allow_nan=False)


@pytest.mark.geometry
@pytest.mark.samples
def test_spanner_curvature_subsegmentation_separates_required_patches() -> None:
    mesh = _spanner_mesh()
    settings = SegmentationSettings(enable_curvature_subsegmentation=True)

    first = segment_mesh(mesh, settings)
    repeated = segment_mesh(mesh, settings)

    assert first.to_dict() == repeated.to_dict()
    assert [patch.id for patch in first.patches] == [patch.id for patch in repeated.patches]
    assert first.counts_by_curvature_class == {
        "planar": 8,
        "cylindrical": 1,
        "fillet-band": 2,
        "freeform": 0,
    }
    planar = [
        patch
        for patch in first.patches
        if patch.curvature_evidence is not None
        and patch.curvature_evidence.curvature_class == "planar"
    ]
    top_and_bottom = sorted(
        (patch for patch in planar if patch.area_mm2 > 1_000.0),
        key=lambda patch: patch.centroid[2],
    )
    hex_walls = [patch for patch in planar if 40.0 < patch.area_mm2 < 60.0]
    assert len(top_and_bottom) == 2
    assert all(patch.kind == "plane" for patch in top_and_bottom)
    assert [patch.centroid[2] for patch in top_and_bottom] == pytest.approx([0.0, 8.0], abs=1e-4)
    assert len(hex_walls) == 6
    assert all(patch.kind == "plane" for patch in hex_walls)

    outer_walls = [
        patch
        for patch in first.patches
        if patch.curvature_evidence is not None
        and patch.curvature_evidence.curvature_class == "cylindrical"
    ]
    assert len(outer_walls) == 1
    assert outer_walls[0].area_mm2 > 900.0
    assert outer_walls[0].curvature_evidence is not None
    assert outer_walls[0].curvature_evidence.absorbed_fragments

    manifest = _spanner_manifest()
    features = manifest["featureTree"]["features"]
    ground_truth_radius = next(
        feature["radius"] for feature in features if feature["id"] == "outer-fillets"
    )
    fillets = [
        patch
        for patch in first.patches
        if patch.curvature_evidence is not None
        and patch.curvature_evidence.curvature_class == "fillet-band"
    ]
    assert len(fillets) == 2
    for patch in fillets:
        evidence = patch.curvature_evidence
        assert evidence is not None
        assert evidence.estimated_minimum_radius_mm == pytest.approx(
            ground_truth_radius,
            rel=0.05,
        )

    assigned = [face_id for patch in first.patches for face_id in patch.triangle_ids]
    assert len(assigned) == len(mesh.faces)
    assert sorted(assigned) == list(range(len(mesh.faces)))
