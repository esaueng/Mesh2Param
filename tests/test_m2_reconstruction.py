from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cadquery as cq
import numpy as np
import pytest
import trimesh
from mesh2param.cli import build_parser, main
from mesh2param.comparison import (
    ComparisonSettings,
    compare_mesh_to_shape,
    write_residual_heatmap_glb,
)
from mesh2param.compiler import compile_cadgraph
from mesh2param.frame import CoordinateFrame, infer_coordinate_frame
from mesh2param.inference import (
    CandidateEvaluation,
    InferredHole,
    build_l_bracket_cadgraph,
    compile_candidate,
    infer_through_holes,
)
from mesh2param.ingest import IngestedMesh, ingest_mesh
from mesh2param.reconstruction import ReconstructionSettings, reconstruct_file
from mesh2param.repair import RepairResult, repair_mesh
from mesh2param.samples import sample_graph, sample_spec, sample_transform
from mesh2param.segmentation import (
    PatchEditSession,
    SegmentationResult,
    SegmentationSettings,
    segment_mesh,
)
from mesh2param.selection import write_patch_selection_artifacts
from mesh2param.sketches import (
    ExtractedSketches,
    InferredProfile,
    extract_planar_sketches,
    infer_l_profile,
)
from mesh2param.tessellation import tessellate_shape, transform_tessellation, write_binary_stl
from mesh2param.validation import (
    classify_face_surfaces,
    export_step_validated,
    import_step_shape,
    validate_shape,
)
from mesh2param_contracts import CADGraph


@dataclass(frozen=True)
class BracketEvidence:
    path: Path
    source: IngestedMesh
    repair: RepairResult
    segmentation: SegmentationResult
    frame: CoordinateFrame
    sketches: ExtractedSketches
    profile: InferredProfile
    holes: tuple[InferredHole, ...]
    graph: CADGraph
    candidate: CandidateEvaluation


@dataclass(frozen=True)
class GeneratedBracket:
    path: Path
    graph: CADGraph
    shape: cq.Shape


def _rigid_vertex(
    rotation: np.ndarray,
    translation: np.ndarray,
    vertex: tuple[float, float, float],
) -> tuple[float, float, float]:
    result = rotation @ np.asarray(vertex) + translation
    return float(result[0]), float(result[1]), float(result[2])


def test_minimum_patch_area_classifies_small_regions_without_aborting() -> None:
    mesh = trimesh.Trimesh(
        vertices=np.asarray(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))),
        faces=np.asarray(((0, 1, 2),)),
        process=False,
    )
    segmentation = segment_mesh(
        mesh,
        SegmentationSettings(minimum_patch_area_mm2=1.0),
    )
    assert len(segmentation.patches) == 1
    assert segmentation.patches[0].kind == "freeform"
    assert segmentation.patches[0].area_mm2 == pytest.approx(0.5)


@pytest.fixture(scope="module")
def generated_bracket(tmp_path_factory: pytest.TempPathFactory) -> GeneratedBracket:
    root = tmp_path_factory.mktemp("m2-bracket")
    spec = sample_spec("l-bracket-with-holes")
    graph = sample_graph(spec.slug)
    compiled = compile_cadgraph(graph)
    assert compiled.success
    mesh = tessellate_shape(compiled.require_shape(), linear_tolerance=0.025, angular_tolerance=0.1)
    transform = sample_transform(spec)
    rotation = np.asarray(transform.rotation)
    translation = np.asarray(transform.translation_mm)
    transformed = transform_tessellation(
        mesh,
        lambda vertex: _rigid_vertex(rotation, translation, vertex),
    )
    path = root / "bracket.random.stl"
    write_binary_stl(transformed, path, linear_tolerance=0.025, angular_tolerance=0.1)
    return GeneratedBracket(path, graph, compiled.require_shape())


@pytest.fixture(scope="module")
def bracket_path(generated_bracket: GeneratedBracket) -> Path:
    return generated_bracket.path


@pytest.fixture(scope="module")
def bracket(bracket_path: Path) -> BracketEvidence:
    source = ingest_mesh(bracket_path)
    repaired = repair_mesh(source)
    segmentation = segment_mesh(repaired.mesh)
    frame = infer_coordinate_frame(repaired.mesh, segmentation.patches)
    sketches = extract_planar_sketches(repaired.mesh, segmentation.patches, frame)
    profile = infer_l_profile(segmentation.patches, sketches, frame)
    holes = infer_through_holes(repaired.mesh, segmentation.patches, frame)
    graph = build_l_bracket_cadgraph(
        source={
            "sha256": source.metadata.sha256,
            "format": source.metadata.format,
            "originalFileName": source.metadata.filename,
            "byteSize": source.metadata.byte_size,
            "triangleCount": source.diagnostics.triangle_count,
            "units": "mm",
            "scaleFactor": 1.0,
        },
        frame=frame,
        profile=profile,
        holes=holes,
    )
    candidate = compile_candidate("measured", graph)
    assert candidate.valid and candidate.shape is not None
    return BracketEvidence(
        bracket_path,
        source,
        repaired,
        segmentation,
        frame,
        sketches,
        profile,
        holes,
        graph,
        candidate,
    )


@pytest.mark.geometry
def test_transform_blind_segmentation_frame_and_feature_dimensions(
    bracket: BracketEvidence,
) -> None:
    assert bracket.segmentation.counts_by_type == {
        "plane": 8,
        "cylinder": 4,
        "freeform": 0,
        "unknown": 0,
    }
    assert bracket.frame.extents_mm == pytest.approx((60.0, 40.0, 45.0), abs=5e-6)
    assert np.asarray(bracket.profile.points_yz_mm) == pytest.approx(
        np.asarray(((0, 0), (40, 0), (40, 6), (6, 6), (6, 45), (0, 45))), abs=5e-6
    )
    assert bracket.profile.extrusion_distance_mm == pytest.approx(60.0, abs=5e-6)
    assert len(bracket.holes) == 4
    assert [hole.diameter_mm for hole in bracket.holes] == pytest.approx([8.0] * 4, abs=5e-6)
    assert [hole.depth_mm for hole in bracket.holes] == pytest.approx([6.0] * 4, abs=5e-6)
    assert np.asarray([hole.position_mm for hole in bracket.holes]) == pytest.approx(
        np.asarray(((15, 25, 6), (45, 25, 6), (15, 6, 27), (45, 6, 27))),
        abs=5e-6,
    )
    result = bracket.candidate
    assert result.valid
    assert result.shape is not None and result.shape.isValid()
    assert result.shape.Volume() == pytest.approx(27233.628421021516, abs=0.01)


@pytest.mark.geometry
def test_patch_ids_survive_face_reordering_and_edits_preserve_failures(
    bracket: BracketEvidence,
) -> None:
    mesh = bracket.repair.mesh
    permutation = np.random.default_rng(42).permutation(len(mesh.faces))
    reordered = trimesh.Trimesh(
        vertices=np.asarray(mesh.vertices).copy(),
        faces=np.asarray(mesh.faces)[permutation],
        process=False,
        validate=False,
    )
    repeated = segment_mesh(reordered)
    assert {patch.id for patch in repeated.patches} == {
        patch.id for patch in bracket.segmentation.patches
    }

    session = PatchEditSession(mesh, bracket.segmentation)
    cylinder = next(patch for patch in bracket.segmentation.patches if patch.kind == "cylinder")
    assert session.lock(cylinder.id).success
    rejected = session.reclassify(cylinder.id, "plane")
    assert not rejected.success and rejected.after == rejected.before

    planes = [patch for patch in bracket.segmentation.patches if patch.kind == "plane"]
    incompatible = session.merge(planes[0].id, planes[-1].id)
    assert not incompatible.success
    assert incompatible.after == incompatible.before


@pytest.mark.geometry
def test_comparison_heatmap_and_hash_bound_patch_selection(
    bracket: BracketEvidence, tmp_path: Path
) -> None:
    compiled = bracket.candidate
    assert compiled.valid and compiled.shape is not None
    transform = np.eye(4)
    transform[:3, :3] = bracket.frame.axes
    transform[:3, 3] = np.asarray(bracket.frame.origin)
    report = compare_mesh_to_shape(
        bracket.repair.mesh,
        compiled.shape,
        transform=transform,
        settings=ComparisonSettings(sample_count_each_direction=96),
    )
    assert report.rms_distance_mm < 3e-6
    assert report.p95_distance_mm < 5e-6
    assert report.p99_distance_mm < 5e-6
    assert report.maximum_distance_mm < 6e-6
    assert report.tolerance_surface_coverage == 1.0

    heatmap_a = write_residual_heatmap_glb(
        bracket.repair.mesh,
        report.source_vertex_residuals_mm,
        tmp_path / "heatmap-a.glb",
        tolerance_mm=0.1,
    )
    heatmap_b = write_residual_heatmap_glb(
        bracket.repair.mesh,
        report.source_vertex_residuals_mm,
        tmp_path / "heatmap-b.glb",
        tolerance_mm=0.1,
    )
    assert heatmap_a.sha256 == heatmap_b.sha256

    first = write_patch_selection_artifacts(
        bracket.repair.mesh,
        bracket.segmentation.patches,
        tmp_path / "patches-a.glb",
        tmp_path / "selection-a.json",
    )
    second = write_patch_selection_artifacts(
        bracket.repair.mesh,
        bracket.segmentation.patches,
        tmp_path / "patches-b.glb",
        tmp_path / "selection-b.json",
    )
    assert first.glb.sha256 == second.glb.sha256
    selection = json.loads((tmp_path / "selection-a.json").read_text())
    assert (
        selection["artifact"]["sha256"]
        == hashlib.sha256((tmp_path / "patches-a.glb").read_bytes()).hexdigest()
    )
    covered = sum(
        item["triangleEndExclusive"] - item["triangleStart"] for item in selection["ranges"]
    )
    assert covered == len(bracket.repair.mesh.faces)
    assert {item["patchId"] for item in selection["ranges"]} == {
        patch.id for patch in bracket.segmentation.patches
    }
    assert all("residualsMm" in metadata for metadata in selection["patches"].values())


@pytest.mark.geometry
def test_coarse_faceted_holes_recover_as_cylinders_while_damage_still_fails(
    bracket: BracketEvidence, tmp_path: Path
) -> None:
    assert bracket.candidate.shape is not None
    shape = bracket.candidate.shape
    spec = sample_spec("l-bracket-with-holes")
    transform = sample_transform(spec)
    rotation = np.asarray(transform.rotation)
    translation = np.asarray(transform.translation_mm)
    coarse = transform_tessellation(
        tessellate_shape(shape, linear_tolerance=0.5, angular_tolerance=0.8),
        lambda vertex: _rigid_vertex(rotation, translation, vertex),
    )
    coarse_mesh = trimesh.Trimesh(coarse.vertices, coarse.triangles, process=False)
    coarse_segmentation = segment_mesh(coarse_mesh)
    recovered_cylinders = [
        patch
        for patch in coarse_segmentation.patches
        if patch.kind == "cylinder" and patch.recovered_from_facets
    ]
    assert len(recovered_cylinders) == 4
    assert all((patch.facet_sagitta_mm or math.inf) < 0.1 for patch in recovered_cylinders)
    coarse_frame = infer_coordinate_frame(coarse_mesh, coarse_segmentation.patches)
    coarse_sketches = extract_planar_sketches(
        coarse_mesh, coarse_segmentation.patches, coarse_frame
    )
    coarse_profile = infer_l_profile(coarse_segmentation.patches, coarse_sketches, coarse_frame)
    coarse_holes = infer_through_holes(coarse_mesh, coarse_segmentation.patches, coarse_frame)
    assert len(coarse_holes) == 4
    assert [hole.diameter_mm for hole in coarse_holes] == pytest.approx([8.0] * 4, abs=1e-5)
    coarse_graph = build_l_bracket_cadgraph(
        source={
            "sha256": "0" * 64,
            "format": "stl",
            "originalFileName": "coarse.stl",
            "byteSize": 1,
            "triangleCount": len(coarse_mesh.faces),
            "units": "mm",
            "scaleFactor": 1.0,
        },
        frame=coarse_frame,
        profile=coarse_profile,
        holes=coarse_holes,
    )
    coarse_candidate = compile_candidate("coarse-cylinder-recovery", coarse_graph)
    assert coarse_candidate.valid and coarse_candidate.shape is not None
    assert classify_face_surfaces(coarse_candidate.shape)["cylinder"] >= 4
    assert export_step_validated(coarse_candidate.shape, tmp_path / "coarse-holes.step").valid

    normals = np.asarray(bracket.repair.mesh.face_normals)
    remove = normals @ rotation[:, 0] > 0.999999
    damaged = trimesh.Trimesh(
        vertices=np.asarray(bracket.repair.mesh.vertices).copy(),
        faces=np.asarray(bracket.repair.mesh.faces)[~remove],
        process=False,
        validate=False,
    )
    damaged_segmentation = segment_mesh(damaged)
    damaged_frame = infer_coordinate_frame(damaged, damaged_segmentation.patches)
    damaged_sketches = extract_planar_sketches(damaged, damaged_segmentation.patches, damaged_frame)
    with pytest.raises(ValueError, match="exactly two matched six-line end loops"):
        infer_l_profile(damaged_segmentation.patches, damaged_sketches, damaged_frame)


def _assert_camel_case_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            assert "_" not in key, f"snake_case serialization key: {key}"
            _assert_camel_case_keys(child)
    elif isinstance(value, list | tuple):
        for child in value:
            _assert_camel_case_keys(child)


def test_public_m2_payloads_are_recursively_camel_case(bracket: BracketEvidence) -> None:
    compiled = bracket.candidate
    payloads = (
        bracket.source.to_dict(),
        bracket.repair.to_dict(),
        bracket.segmentation.to_dict(),
        bracket.frame.to_dict(),
        bracket.sketches.to_dict(),
        bracket.holes[0].to_dict(),
        compiled.to_dict(),
    )
    for payload in payloads:
        _assert_camel_case_keys(payload)


ACCEPTANCE_SEQUENCE = (
    "generate bracket CADGraph",
    "export exact STEP",
    "tessellate source",
    "reconstruct mesh",
    "build proposal",
    "valid B-Rep",
    "export STEP",
    "reimport",
    "valid solid",
    "compare",
    "major dimension +10%",
    "rebuild",
    "valid solid",
    "restore",
    "rebuild",
    "metrics return close",
)


@pytest.mark.geometry
def test_geometry_acceptance_exact_sixteen_step_sequence(
    generated_bracket: GeneratedBracket,
    bracket: BracketEvidence,
    tmp_path: Path,
) -> None:
    assert len(ACCEPTANCE_SEQUENCE) == 16
    exact_graph = generated_bracket.graph  # 1 generate bracket CADGraph
    assert exact_graph.id == "sample.l-bracket-with-holes"
    exact_step = export_step_validated(  # 2 export exact STEP
        generated_bracket.shape, tmp_path / "source-exact.step"
    )
    assert exact_step.valid
    source_mesh = bracket.repair.mesh  # 3 tessellate source (fixture uses exact shape + seed)
    assert len(source_mesh.faces) > 0 and source_mesh.is_watertight
    assert bracket.segmentation.counts_by_type["plane"] == 8  # 4 reconstruct mesh
    assert bracket.segmentation.counts_by_type["cylinder"] == 4
    proposal = bracket.graph  # 5 build proposal
    assert bracket.candidate.shape is not None and bracket.candidate.valid  # 6 valid B-Rep
    proposal_step = export_step_validated(  # 7 export STEP
        bracket.candidate.shape, tmp_path / "proposal.step"
    )
    reimported = import_step_shape(proposal_step.path)  # 8 reimport
    reimport_validation = validate_shape(reimported)  # 9 valid solid
    assert reimport_validation.valid and reimport_validation.solid_count == 1
    transform = np.eye(4)
    transform[:3, :3] = bracket.frame.axes
    transform[:3, 3] = np.asarray(bracket.frame.origin)
    initial_metrics = compare_mesh_to_shape(  # 10 compare
        source_mesh,
        bracket.candidate.shape,
        transform=transform,
        settings=ComparisonSettings(sample_count_each_direction=96),
    )
    document = proposal.model_dump(mode="json", by_alias=True)
    hole = next(feature for feature in document["features"] if feature["operation"] == "hole")
    measured_diameter = hole["diameter"]
    hole["diameter"] = measured_diameter * 1.1  # 11 major dimension +10%
    edited = CADGraph.model_validate(document)
    edited_result = compile_cadgraph(edited)  # 12 rebuild
    edited_validation = validate_shape(edited_result.require_shape())  # 13 valid solid
    assert edited_result.success and edited_validation.valid
    hole["diameter"] = measured_diameter  # 14 restore
    restored = CADGraph.model_validate(document)
    restored_result = compile_cadgraph(restored)  # 15 rebuild
    assert restored_result.success and restored_result.require_shape().isValid()
    restored_metrics = compare_mesh_to_shape(  # 16 metrics return close
        source_mesh,
        restored_result.require_shape(),
        transform=transform,
        settings=ComparisonSettings(sample_count_each_direction=96),
    )
    assert restored_metrics.p95_distance_mm < 5e-6
    assert restored_metrics.maximum_distance_mm < 6e-6
    assert restored_metrics.rms_distance_mm == pytest.approx(
        initial_metrics.rms_distance_mm, abs=1e-12
    )


@pytest.mark.geometry
def test_reconstruction_orchestrator_writes_valid_artifact_bundle(
    bracket_path: Path, tmp_path: Path
) -> None:
    result = reconstruct_file(
        bracket_path,
        tmp_path,
        settings=ReconstructionSettings(
            comparison=ComparisonSettings(sample_count_each_direction=64),
            include_nominal_preview=False,
        ),
    )
    assert result.graph.validation.status == "valid"
    assert result.step.valid
    assert result.selected.label == "measured"
    assert result.comparison.p95_distance_mm < 5e-6
    required = {
        "analysis.json",
        "source.glb",
        "repair.json",
        "repaired.glb",
        "analysis-proxy.glb",
        "patches.json",
        "patches.glb",
        "selection-map.json",
        "frame.json",
        "sketches.json",
        "candidates.json",
        "model.cadgraph.json",
        "model.cq.py",
        "model.step",
        "model.glb",
        "comparison.json",
        "residual-heatmap.glb",
        "reconstruction.json",
        "manifest.json",
    }
    assert required <= {path.name for path in tmp_path.iterdir()}
    candidate_documents = json.loads((tmp_path / "candidates.json").read_text(encoding="utf-8"))
    assert candidate_documents
    assert all(CADGraph.model_validate(item["cadgraph"]) for item in candidate_documents)


def test_cli_exposes_exact_m2_commands_and_service_arguments(
    capsys: pytest.CaptureFixture[str], bracket_path: Path, tmp_path: Path
) -> None:
    help_text = build_parser().format_help()
    for command in (
        "analyze",
        "repair",
        "segment",
        "reconstruct",
        "rebuild",
        "compare",
        "validate",
        "samples",
        "serve",
    ):
        assert command in help_text
    assert main(["analyze", str(bracket_path), "--units", "mm", "--output", str(tmp_path)]) == 0
    assert (tmp_path / "analysis.json").is_file()
    capsys.readouterr()
    serve = build_parser().parse_args(["serve", "--host", "127.0.0.1", "--port", "8765"])
    assert serve.host == "127.0.0.1"
    assert serve.port == 8765
