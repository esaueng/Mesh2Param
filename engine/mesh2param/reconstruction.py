"""Shared M2 reconstruction orchestration used by the CLI and future API workers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from mesh2param_contracts import CADGraph, canonical_json_bytes

from .comparison import (
    ComparisonReport,
    ComparisonSettings,
    compare_mesh_to_shape,
    write_residual_heatmap_glb,
)
from .frame import CoordinateFrame, FrameInferenceError, infer_coordinate_frame
from .inference import (
    CandidateEvaluation,
    CandidateSearchSettings,
    InferredHole,
    build_l_bracket_cadgraph,
    compile_candidate,
    infer_through_holes,
    score_candidate,
    select_bounded_candidates,
)
from .ingest import IngestedMesh, MeshLimits, ingest_mesh
from .repair import RepairResult, RepairSettings, repair_mesh
from .segmentation import SegmentationResult, SegmentationSettings, segment_mesh
from .selection import SelectionMapArtifact, write_patch_selection_artifacts
from .sketches import (
    ExtractedSketches,
    InferredProfile,
    SketchExtractionSettings,
    extract_planar_sketches,
    infer_l_profile,
)
from .source import write_cadquery_source
from .tessellation import Tessellation, export_glb, write_binary_stl
from .validation import StepValidation, export_step_validated


@dataclass(frozen=True, slots=True)
class ReconstructionSettings:
    mesh_limits: MeshLimits = field(default_factory=MeshLimits)
    repair: RepairSettings = field(default_factory=RepairSettings)
    segmentation: SegmentationSettings = field(default_factory=SegmentationSettings)
    sketches: SketchExtractionSettings = field(default_factory=SketchExtractionSettings)
    comparison: ComparisonSettings = field(default_factory=ComparisonSettings)
    candidate_search: CandidateSearchSettings = field(default_factory=CandidateSearchSettings)
    include_nominal_preview: bool = True


class ReconstructionError(ValueError):
    def __init__(self, stage: str, code: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.code = code

    def to_dict(self) -> dict[str, str]:
        return {"stage": self.stage, "code": self.code, "message": str(self)}


@dataclass(slots=True)
class ReconstructionResult:
    source: IngestedMesh
    repair: RepairResult
    segmentation: SegmentationResult
    frame: CoordinateFrame
    sketches: ExtractedSketches
    profile: InferredProfile
    holes: tuple[InferredHole, ...]
    candidates: tuple[CandidateEvaluation, ...]
    selected: CandidateEvaluation
    graph: CADGraph
    comparison: ComparisonReport
    step: StepValidation
    patch_selection: SelectionMapArtifact
    artifacts: dict[str, str]
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "valid",
            "scope": "transform-blind sharp-edged plane/full-cylinder L-bracket",
            "source": self.source.to_dict(),
            "repair": self.repair.to_dict(),
            "segmentation": self.segmentation.to_dict(),
            "coordinateFrame": self.frame.to_dict(),
            "sketchExtraction": self.sketches.to_dict(),
            "featureInference": {
                "profileYZMm": [list(point) for point in self.profile.points_yz_mm],
                "extrusionDistanceMm": self.profile.extrusion_distance_mm,
                "holes": [hole.to_dict() for hole in self.holes],
            },
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "selectedCandidate": self.selected.label,
            "comparison": self.comparison.to_dict(),
            "stepValidation": self.step.to_dict(),
            "patchSelection": self.patch_selection.to_dict(),
            "artifacts": dict(sorted(self.artifacts.items())),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _source_document(source: IngestedMesh, units: str) -> dict[str, Any]:
    return {
        "sha256": source.metadata.sha256,
        "format": source.metadata.format,
        "originalFileName": source.metadata.filename,
        "byteSize": source.metadata.byte_size,
        "triangleCount": source.diagnostics.triangle_count,
        "units": units,
        "scaleFactor": 1.0,
    }


def _world_transform(frame: CoordinateFrame) -> np.ndarray:
    transform = np.eye(4)
    transform[:3, :3] = frame.axes
    transform[:3, 3] = np.asarray(frame.origin)
    return transform


def _final_graph(
    graph: CADGraph,
    comparison: ComparisonReport,
    step: StepValidation,
    selected_feature_id: str,
    warnings: tuple[str, ...],
) -> CADGraph:
    document = graph.model_dump(mode="json", by_alias=True)
    relative_volume = comparison.relative_volume_delta
    document["fitMetrics"] = {
        "rmsSurfaceDistance": comparison.rms_distance_mm,
        "p95SurfaceDistance": comparison.p95_distance_mm,
        "maxSurfaceDistance": comparison.maximum_distance_mm,
        "normalAgreement": comparison.mean_normal_agreement,
        "volumeDifference": (
            comparison.absolute_volume_delta_mm3
            if comparison.absolute_volume_delta_mm3 is not None
            else 0.0
        ),
        "overlap": comparison.tolerance_surface_coverage,
        "unmatchedSourceArea": comparison.source_unmatched_area_estimate_mm2,
        "excessResultArea": comparison.result_excess_area_estimate_mm2,
        "score": max(
            0.0,
            1.0
            - comparison.rms_distance_mm / graph.project_tolerance.surface_deviation
            - (relative_volume if relative_volume is not None else 1.0),
        ),
    }
    tolerance_satisfied = (
        comparison.p95_distance_mm <= graph.project_tolerance.surface_deviation
        and comparison.maximum_distance_mm <= graph.project_tolerance.surface_deviation
    )
    document["validation"] = {
        "status": "valid" if step.valid and tolerance_satisfied else "invalid",
        "brepValid": step.source.valid,
        "stepReimportValid": step.reimport.valid,
        "toleranceSatisfied": tolerance_satisfied,
        "checkedAt": "1970-01-01T00:00:00Z",
        "lastValidFeatureId": selected_feature_id,
        "issues": [
            {
                "code": "reconstruction-warning",
                "message": warning,
                "severity": "warning",
            }
            for warning in warnings
        ],
    }
    return CADGraph.model_validate(document)


def _mesh_tessellation(mesh: Any) -> Tessellation:
    vertices = tuple(tuple(float(value) for value in vertex) for vertex in mesh.vertices)
    triangles = tuple(tuple(int(value) for value in face) for face in mesh.faces)
    return Tessellation(vertices, triangles, ())  # type: ignore[arg-type]


def _manifest(output: Path, artifacts: dict[str, str]) -> dict[str, Any]:
    records = []
    for name, raw_path in sorted(artifacts.items()):
        path = Path(raw_path)
        payload = path.read_bytes()
        records.append(
            {
                "name": name,
                "path": path.name,
                "byteSize": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    result = {"schemaVersion": "1.0.0", "directory": str(output), "artifacts": records}
    _write_json(output / "manifest.json", result)
    return result


def reconstruct_file(
    source_path: str | Path,
    output_directory: str | Path,
    *,
    units: str = "mm",
    settings: ReconstructionSettings | None = None,
) -> ReconstructionResult:
    """Run the verified bracket pipeline and write truthful intermediate artifacts."""

    settings = settings or ReconstructionSettings()
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    completed: dict[str, Any] = {}
    try:
        source = ingest_mesh(source_path, limits=settings.mesh_limits)
        original_path = output / f"source.original{source.metadata.extension}"
        original_path.write_bytes(source.original_bytes)
        completed["source"] = source.to_dict()
        _write_json(output / "analysis.json", source.to_dict())

        repaired = repair_mesh(source, settings.repair, limits=settings.mesh_limits)
        completed["repair"] = repaired.to_dict()
        _write_json(output / "repair.json", repaired.to_dict())
        repaired_path = output / "repaired.stl"
        write_binary_stl(_mesh_tessellation(repaired.mesh), repaired_path)

        segmentation = segment_mesh(repaired.mesh, settings.segmentation)
        completed["segmentation"] = segmentation.to_dict()
        _write_json(output / "patches.json", segmentation.to_dict())

        if segmentation.counts_by_type["freeform"] or segmentation.counts_by_type["unknown"]:
            raise ReconstructionError(
                "segmentation",
                "unsupported-freeform-remainder",
                "automatic L-bracket inference requires only plane and full-cylinder patches",
            )
        frame = infer_coordinate_frame(repaired.mesh, segmentation.patches)
        completed["coordinateFrame"] = frame.to_dict()
        _write_json(output / "frame.json", frame.to_dict())

        sketches = extract_planar_sketches(
            repaired.mesh, segmentation.patches, frame, settings.sketches
        )
        completed["sketchExtraction"] = sketches.to_dict()
        _write_json(output / "sketches.json", sketches.to_dict())
        if any(loop.kind == "openBoundary" for loop in sketches.loops):
            raise ReconstructionError(
                "sketch-extraction",
                "open-patch-boundary",
                "damaged/open patch loops are preserved but not automatically closed",
            )
        profile = infer_l_profile(segmentation.patches, sketches, frame)
        holes = infer_through_holes(repaired.mesh, segmentation.patches, frame)
        if len(holes) != 4:
            raise ReconstructionError(
                "feature-inference",
                "unsupported-hole-count",
                f"verified L-bracket scope requires four through holes; found {len(holes)}",
            )

        measured = compile_candidate(
            "measured",
            build_l_bracket_cadgraph(
                source=_source_document(source, units),
                frame=frame,
                profile=profile,
                holes=holes,
                use_nominal_preview=False,
            ),
        )
        generated_candidates = [measured]
        if settings.include_nominal_preview:
            generated_candidates.append(
                compile_candidate(
                    "nominal-preview",
                    build_l_bracket_cadgraph(
                        source=_source_document(source, units),
                        frame=frame,
                        profile=profile,
                        holes=holes,
                        use_nominal_preview=True,
                    ),
                )
            )
        transform = _world_transform(frame)
        for candidate in generated_candidates:
            if candidate.valid and candidate.shape is not None:
                comparison = compare_mesh_to_shape(
                    repaired.mesh,
                    candidate.shape,
                    transform=transform,
                    settings=settings.comparison,
                )
                score_candidate(candidate, comparison)
        candidates = select_bounded_candidates(generated_candidates, settings.candidate_search)
        if not candidates:
            raise ReconstructionError(
                "candidate-search",
                "no-valid-brep",
                "every bounded candidate was rejected by the CAD kernel",
            )
        selected = candidates[0]
        if selected.shape is None or selected.comparison is None:
            raise AssertionError("selected candidate is missing validated geometry or comparison")
        comparison = selected.comparison
        completed["candidates"] = [candidate.to_dict() for candidate in candidates]
        _write_json(output / "candidates.json", completed["candidates"])

        step_path = output / "model.step"
        step = export_step_validated(selected.shape, step_path, units=units)
        warnings = tuple(
            dict.fromkeys(
                [warning.message for warning in source.diagnostics.warnings]
                + list(repaired.warnings)
                + list(segmentation.warnings)
                + list(sketches.warnings)
                + list(comparison.warnings)
            )
        )
        graph = _final_graph(
            selected.graph,
            comparison,
            step,
            selected.graph.features[-1].id,
            warnings,
        )
        graph_path = output / "model.cadgraph.json"
        graph_path.write_bytes(canonical_json_bytes(graph))
        source_path_output = output / "model.cq.py"
        write_cadquery_source(graph, source_path_output)
        result_glb = output / "model.glb"
        export_glb(selected.shape, result_glb)
        heatmap_path = output / "residual-heatmap.glb"
        heatmap = write_residual_heatmap_glb(
            repaired.mesh,
            comparison.source_vertex_residuals_mm,
            heatmap_path,
            tolerance_mm=settings.comparison.tolerance_mm,
        )
        patch_selection = write_patch_selection_artifacts(
            repaired.mesh,
            segmentation.patches,
            output / "patches.glb",
            output / "selection-map.json",
        )
        _write_json(output / "comparison.json", comparison.to_dict())
        artifacts = {
            "analysis": str(output / "analysis.json"),
            "repair": str(output / "repair.json"),
            "repairedMesh": str(repaired_path),
            "patches": str(output / "patches.json"),
            "patchesGlb": patch_selection.glb.path,
            "selectionMap": patch_selection.path,
            "frame": str(output / "frame.json"),
            "sketches": str(output / "sketches.json"),
            "candidates": str(output / "candidates.json"),
            "cadgraph": str(graph_path),
            "cadquerySource": str(source_path_output),
            "step": str(step_path),
            "modelGlb": str(result_glb),
            "comparison": str(output / "comparison.json"),
            "residualHeatmap": heatmap.path,
            "originalSource": str(original_path),
        }
        limitations = (
            "Only a single sharp-edged, plane/full-cylinder L-bracket with four through "
            "holes is inferred automatically.",
            "Equal extents, partial cylinders, freeform remainder, fillets, chamfers, and "
            "damaged loops require user correction.",
            "X polarity may remain tied for an X-symmetric bracket.",
            "Reconstructed feature-face selection is deferred until semantic topology can "
            "map final faces without guessing; patch selection is hash-bound.",
        )
        result = ReconstructionResult(
            source,
            repaired,
            segmentation,
            frame,
            sketches,
            profile,
            holes,
            candidates,
            selected,
            graph,
            comparison,
            step,
            patch_selection,
            artifacts,
            warnings,
            limitations,
        )
        _write_json(output / "reconstruction.json", result.to_dict())
        artifacts["reconstruction"] = str(output / "reconstruction.json")
        _manifest(output, artifacts)
        return result
    except ReconstructionError as exc:
        partial = {
            "status": "partial",
            "error": exc.to_dict(),
            "completedStages": completed,
            "limitations": [
                "No inferred CADGraph or STEP is claimed when bounded evidence checks fail."
            ],
        }
        _write_json(output / "reconstruction.partial.json", partial)
        raise
    except FrameInferenceError as exc:
        wrapped = ReconstructionError("coordinate-frame", "ambiguous-frame", str(exc))
        _write_json(
            output / "reconstruction.partial.json",
            {
                "status": "partial",
                "error": wrapped.to_dict(),
                "completedStages": completed,
            },
        )
        raise wrapped from exc
    except ValueError as exc:
        wrapped = ReconstructionError("reconstruction", "bounded-inference-failed", str(exc))
        _write_json(
            output / "reconstruction.partial.json",
            {
                "status": "partial",
                "error": wrapped.to_dict(),
                "completedStages": completed,
            },
        )
        raise wrapped from exc


__all__ = [
    "ReconstructionError",
    "ReconstructionResult",
    "ReconstructionSettings",
    "reconstruct_file",
]
