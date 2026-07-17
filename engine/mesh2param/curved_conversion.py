"""Source-bound curved reconstruction conversion for the service layer.

Mirrors the faceted fallback's contract: preserve and verify the exact source
upload, run the curved plate reconstruction, emit a CADGraph whose base
feature is ``reconstructedSurfaceNetwork`` referencing the content-addressed
curved-plate artifact, and prove the graph by compiling it through the same
trusted compiler the API and CLI use. The result is explicitly an
**approximate curved B-Rep**: a tolerance-controlled approximation of the
source mesh, never recovered design history, and every artifact and label
says so.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import trimesh
from mesh2param_contracts import CADGraph, canonical_json_bytes

from .compiler import CompilationResult, compile_cadgraph
from .curved_patch import (
    CurvedNetworkResult,
    CurvedNetworkSettings,
    CurvedPatchError,
    CurvedPatchSettings,
    ProgressCallback,
    plate_artifact_bytes,
    plate_artifact_payload,
    plate_artifact_sha256,
    reconstruct_plate_network,
)
from .fit_cache import CurvedFitCache
from .ingest import IngestedMesh, MeshLimits, ingest_mesh
from .repair import RepairResult, repair_mesh
from .source import write_cadquery_source
from .step_audit import StepAudit, audit_step_file
from .tessellation import Tessellation, tessellate_shape, write_glb
from .units import millimeters_to_project_units, project_units_to_millimeters
from .validation import StepValidation, export_step_validated

CURVED_ARTIFACT_ID = "artifact.curved-plate"
FIXED_TIMESTAMP = "1970-01-01T00:00:00Z"
APPROXIMATE_SCOPE = "approximate curved B-Rep"


class CurvedConversionError(ValueError):
    """A fail-closed curved conversion error with a stable code and phase."""

    def __init__(self, phase: str, code: str, message: str) -> None:
        super().__init__(message)
        self.phase = phase
        self.code = code


@dataclass(frozen=True, slots=True)
class CurvedConversionResult:
    source: IngestedMesh
    repair: RepairResult
    reconstruction: CurvedNetworkResult
    graph: CADGraph
    compilation: CompilationResult
    step: StepValidation
    audit: StepAudit
    units: str
    artifacts: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "valid",
            "scope": APPROXIMATE_SCOPE,
            "source": self.source.to_dict(),
            "repair": self.repair.to_dict(),
            "reconstruction": self.reconstruction.to_dict(),
            "cadgraph": self.graph.model_dump(mode="json", by_alias=True),
            "compilation": self.compilation.to_dict(),
            "stepValidation": self.step.to_dict(),
            "stepAudit": self.audit.to_dict(),
            "artifacts": dict(sorted(self.artifacts.items())),
            "limitations": [
                "The curved result is a tolerance-controlled approximation inferred "
                "from the tessellated source, not the recovered original CAD "
                "surfaces or design history.",
                "Only single freeform-topped plate topology (with optional "
                "recognized through holes) is reconstructed automatically.",
            ],
        }


def _vector(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": x, "y": y, "z": z}


def _mesh_tessellation(mesh: Any) -> Tessellation:
    vertices = cast(
        tuple[tuple[float, float, float], ...],
        tuple(tuple(float(value) for value in vertex) for vertex in mesh.vertices),
    )
    triangles = cast(
        tuple[tuple[int, int, int], ...],
        tuple(tuple(int(value) for value in face) for face in mesh.faces),
    )
    return Tessellation(vertices, triangles, ())


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _build_graph(
    source: IngestedMesh,
    *,
    units: str,
    source_descriptor: Mapping[str, Any],
    reconstruction: CurvedNetworkResult,
    artifact_sha256: str,
    settings: CurvedPatchSettings,
) -> CADGraph:
    comparison = reconstruction.comparison
    deviation_mm = project_units_to_millimeters(settings.surface_deviation_tolerance_mm, units)
    linear_resolution = min(
        millimeters_to_project_units(0.001, units),
        settings.sewing_tolerance_mm,
    )
    feature_id = "feature.curved-plate"
    topology_id = f"{feature_id}.result"
    evidence_id = "evidence.curved-plate"
    volume_difference = (
        abs(comparison.absolute_volume_delta_mm3)
        if comparison.absolute_volume_delta_mm3 is not None
        else 0.0
    )
    document: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "id": "reconstruction.curved-plate",
        "name": "Curved reconstruction (approximate)",
        "units": units,
        "source": {
            "format": source_descriptor["format"],
            "sha256": source.metadata.sha256,
            "originalFileName": source_descriptor["originalFileName"],
            "byteSize": source.metadata.byte_size,
            "triangleCount": source.diagnostics.triangle_count,
            "declaredUnits": source_descriptor["declaredUnits"],
            "scaleFactor": source_descriptor["scaleFactor"],
        },
        "sourceCoordinateFrame": {
            "origin": _vector(0.0, 0.0, 0.0),
            "xAxis": _vector(1.0, 0.0, 0.0),
            "yAxis": _vector(0.0, 1.0, 0.0),
            "zAxis": _vector(0.0, 0.0, 1.0),
            "locked": True,
            "confidence": 1.0,
            "evidenceIds": [evidence_id],
        },
        "projectTolerance": {
            "surfaceDeviation": settings.surface_deviation_tolerance_mm,
            "angularDeviationDeg": 1.0,
            "linearResolution": linear_resolution,
        },
        "sketches": [],
        "features": [
            {
                "id": feature_id,
                "name": "Reconstructed surface network",
                "operation": "reconstructedSurfaceNetwork",
                "order": 0,
                "dependencies": [],
                "suppressed": False,
                "sourceEvidence": [evidence_id],
                "confidence": 1.0,
                "userLocks": [],
                "overrides": [],
                "semanticOutputs": [topology_id],
                "sourceArtifactId": CURVED_ARTIFACT_ID,
                "artifactSha256": artifact_sha256,
            }
        ],
        "semanticTopology": [
            {
                "id": topology_id,
                "kind": "solid",
                "producerFeatureId": feature_id,
                "role": "resultSolid",
                "generatedFrom": [evidence_id],
                "status": "unresolved",
            }
        ],
        "sourceEvidence": [
            {
                "id": evidence_id,
                "sourceType": "derived",
                "sourceIds": [],
                "residual": comparison.maximum_distance_mm,
                "confidence": 1.0,
                "notes": (
                    "Approximate curved B-Rep fitted to the tessellated source "
                    "within an explicit deviation tolerance; not recovered design "
                    "history."
                ),
                "metadata": {
                    "meshSha256": source.metadata.sha256,
                    "scope": APPROXIMATE_SCOPE,
                    "artifactSha256": artifact_sha256,
                    "faceSurfaces": dict(reconstruction.face_surfaces),
                    "patchCount": len(reconstruction.network.patches),
                    "sharedCurveCount": len(reconstruction.network.curves),
                    "holeCount": len(reconstruction.holes),
                    "residualMaximumMm": reconstruction.residual_maximum,
                    "residualRmsMm": reconstruction.residual_rms,
                    "deviationToleranceMm": deviation_mm,
                    "candidates": [dict(item) for item in reconstruction.candidates],
                    "cacheStatus": reconstruction.cache_status,
                },
            }
        ],
        "userLocks": [],
        "overrides": [],
        "reconstructionSettings": {
            "maxFeatures": 1,
            "beamWidth": 1,
            "candidatesPerResidual": 1,
            "wallClockSeconds": settings.budget.wall_clock_seconds,
            "maxRebuilds": 1,
            "minScoreImprovement": 0.0,
            "nominalSnappingEnabled": False,
            "nominalSnapTolerance": 0.0,
            "scoreWeights": {
                "rmsDistance": 1.0,
                "p95Distance": 1.0,
                "maxDistance": 1.0,
                "normalAgreement": 0.0,
                "volumeDifference": 0.0,
                "overlap": 0.0,
                "sharpEdgeAlignment": 0.0,
                "boundaryAlignment": 0.0,
                "unmatchedSource": 0.0,
                "excessResult": 0.0,
                "complexity": 0.0,
                "unsupportedOperation": 0.0,
                "evidenceConfidence": 0.0,
            },
        },
        "engineVersions": {
            "mesh2param": "0.1.0",
            "contracts": "1.0.0",
            "cadBackend": "OCCT",
            "cadQuery": "2.8.0",
            "ocp": "7.9.3.1.1",
            "dependencies": {
                "numpy": np.__version__,
                "trimesh": trimesh.__version__,
            },
        },
        "deterministicSeed": 0x4D325043,
        "fitMetrics": {
            "rmsSurfaceDistance": comparison.rms_distance_mm,
            "p95SurfaceDistance": comparison.p95_distance_mm,
            "maxSurfaceDistance": comparison.maximum_distance_mm,
            "normalAgreement": comparison.mean_normal_agreement,
            "volumeDifference": volume_difference,
            "overlap": comparison.tolerance_surface_coverage,
            "unmatchedSourceArea": comparison.source_unmatched_area_estimate_mm2,
            "excessResultArea": comparison.result_excess_area_estimate_mm2,
            "score": 0.0,
        },
        "validation": {
            "status": "notRun",
            "brepValid": None,
            "stepReimportValid": None,
            "toleranceSatisfied": None,
            "lastValidFeatureId": None,
            "issues": [],
        },
        "versionMetadata": {
            "versionId": "version.curved-plate.1",
            "createdAt": FIXED_TIMESTAMP,
            "createdBy": "mesh2param-curved-reconstruction",
            "message": "Approximate curved B-Rep reconstructed from the preserved source mesh.",
        },
        "extensions": {
            "mesh2param.dev/curvedReconstruction": {
                "scope": APPROXIMATE_SCOPE,
                "approximate": True,
                "designHistoryRecovered": False,
                "artifactSchema": "mesh2param/curved-plate/1",
                "artifactSha256": artifact_sha256,
                "browserTessellation": "kernel-result",
                "browserTessellationRepresentsKernelResult": True,
            }
        },
    }
    return CADGraph.model_validate(document)


def _validated_graph(
    graph: CADGraph, step: StepValidation, reconstruction: CurvedNetworkResult
) -> CADGraph:
    document = graph.model_dump(mode="json", by_alias=True)
    tolerance = document["projectTolerance"]["surfaceDeviation"]
    satisfied = reconstruction.comparison.maximum_distance_mm <= tolerance
    document["validation"] = {
        "status": "valid" if step.valid and satisfied else "partial",
        "brepValid": step.source.valid,
        "stepReimportValid": step.reimport.valid,
        "toleranceSatisfied": satisfied,
        "checkedAt": FIXED_TIMESTAMP,
        "lastValidFeatureId": "feature.curved-plate",
        "issues": [
            {
                "code": "approximate-curved",
                "message": (
                    "Geometry is valid within the requested tolerance, but the "
                    "curved surfaces are approximations inferred from facets; no "
                    "design history is recovered."
                ),
                "severity": "info",
                "featureId": "feature.curved-plate",
            }
        ],
    }
    return CADGraph.model_validate(document)


def _verified_descriptor(
    source: IngestedMesh,
    source_descriptor: Mapping[str, Any] | None,
    units: str,
) -> dict[str, Any]:
    descriptor = dict(source_descriptor or {})
    declared_units = descriptor.get("declaredUnits", units)
    scale_factor = descriptor.get("scaleFactor", 1.0)
    described_format = descriptor.get("format", source.metadata.format)
    described_sha = descriptor.get("sha256", source.metadata.sha256)
    original_file_name = descriptor.get("originalFileName", source.metadata.filename)
    if (
        described_format != source.metadata.format
        or described_sha != source.metadata.sha256
        or not isinstance(original_file_name, str)
        or not original_file_name.strip()
        or len(original_file_name) > 255
    ):
        raise CurvedConversionError(
            "validating upload",
            "curved_source_metadata_mismatch",
            "The preserved source descriptor does not match the immutable STL bytes.",
        )
    if (
        not isinstance(declared_units, str)
        or declared_units != units
        or isinstance(scale_factor, bool)
        or not isinstance(scale_factor, (int, float))
        or not math.isfinite(float(scale_factor))
        or not math.isclose(float(scale_factor), 1.0, rel_tol=0.0, abs_tol=1e-12)
    ):
        raise CurvedConversionError(
            "normalizing source units",
            "curved_source_transform_unsupported",
            "Curved reconstruction requires source units to match project units "
            "and a scale factor of exactly 1; normalize a working copy first.",
        )
    return {
        "format": source.metadata.format,
        "sha256": source.metadata.sha256,
        "originalFileName": original_file_name,
        "declaredUnits": declared_units,
        "scaleFactor": float(scale_factor),
    }


def create_curved_conversion(
    source_path: str | Path,
    output_directory: str | Path,
    *,
    units: str = "mm",
    settings: CurvedPatchSettings | None = None,
    network_settings: CurvedNetworkSettings | None = None,
    source_descriptor: Mapping[str, Any] | None = None,
    mesh_limits: MeshLimits | None = None,
    progress: ProgressCallback | None = None,
    should_cancel: Any = None,
    fit_cache: CurvedFitCache | None = None,
) -> CurvedConversionResult:
    """Convert a preserved STL upload into a compiled approximate curved B-Rep."""

    settings = settings or CurvedPatchSettings()
    network_settings = network_settings or CurvedNetworkSettings()
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    source = ingest_mesh(source_path, limits=mesh_limits or MeshLimits())
    if source.metadata.format != "stl":
        raise CurvedConversionError(
            "validating upload",
            "unsupported_curved_format",
            "Curved reconstruction currently supports STL sources only.",
        )
    descriptor = _verified_descriptor(source, source_descriptor, units)

    original_path = output / "source.original.stl"
    original_path.write_bytes(source.original_bytes)
    repair = repair_mesh(source, limits=mesh_limits or MeshLimits())
    _write_json(output / "analysis.json", source.to_dict())
    _write_json(output / "repair.json", repair.to_dict())
    write_glb(_mesh_tessellation(source.mesh), output / "source.glb")

    working_mesh = trimesh.Trimesh(
        vertices=np.asarray(source.mesh.vertices, dtype=np.float64),
        faces=np.asarray(source.mesh.faces, dtype=np.int64),
        process=True,
        validate=False,
    )
    try:
        reconstruction = reconstruct_plate_network(
            working_mesh,
            settings=settings,
            network_settings=network_settings,
            progress=progress,
            should_cancel=should_cancel,
            fit_cache=fit_cache,
            source_sha256=source.metadata.sha256,
        )
    except CurvedPatchError as exc:
        raise CurvedConversionError(exc.phase, exc.code, str(exc)) from exc

    payload = plate_artifact_payload(reconstruction, units=units)
    artifact_sha = plate_artifact_sha256(payload)
    artifact_path = output / "curved-plate.json"
    artifact_path.write_bytes(plate_artifact_bytes(payload))

    graph = _build_graph(
        source,
        units=units,
        source_descriptor=descriptor,
        reconstruction=reconstruction,
        artifact_sha256=artifact_sha,
        settings=settings,
    )
    resolver = {CURVED_ARTIFACT_ID: artifact_path}
    compilation = compile_cadgraph(graph, artifact_resolver=resolver)
    if not compilation.success:
        error = compilation.errors[0] if compilation.errors else None
        raise CurvedConversionError(
            "assembling solid",
            error.code if error is not None else "curved_compile_failed",
            error.kernel_error if error is not None else "OCCT rejected the curved plate.",
        )
    shape = compilation.require_shape()

    try:
        step = export_step_validated(
            shape,
            output / "model.step",
            units=units,
            linear_resolution=graph.project_tolerance.linear_resolution,
        )
    except ValueError as exc:
        raise CurvedConversionError(
            "reimporting STEP", "curved_step_validation_failed", str(exc)
        ) from exc

    audit = audit_step_file(output / "model.step")
    if not audit.valid:
        raise CurvedConversionError(
            "reimporting STEP",
            "curved_step_audit_failed",
            "; ".join(audit.errors),
        )

    tessellation = tessellate_shape(shape, linear_tolerance=0.002, angular_tolerance=0.2)
    write_glb(tessellation, output / "reconstructed.glb")

    graph = _validated_graph(graph, step, reconstruction)
    graph_path = output / "model.cadgraph.json"
    graph_path.write_bytes(canonical_json_bytes(graph))
    write_cadquery_source(
        graph,
        output / "model.cq.py",
        artifact_paths={CURVED_ARTIFACT_ID: "curved-plate.json"},
    )

    validation = {
        "status": "valid" if step.valid else "invalid",
        "brepValid": step.source.valid,
        "stepReimportValid": step.reimport.valid,
        "toleranceSatisfied": bool(
            reconstruction.comparison.maximum_distance_mm <= settings.surface_deviation_tolerance_mm
        ),
        "step": step.to_dict(),
        "stepAudit": audit.to_dict(),
        "compilation": compilation.to_dict(),
        "curvedReconstruction": {
            "scope": APPROXIMATE_SCOPE,
            "approximate": True,
            "designHistoryRecovered": False,
            "faceSurfaces": dict(reconstruction.face_surfaces),
            "residualMaximumMm": reconstruction.residual_maximum,
            "comparison": reconstruction.comparison.to_dict(),
            "browserTessellation": "kernel-result",
            "browserTessellationRepresentsKernelResult": True,
        },
    }
    _write_json(output / "validation.json", validation)
    _write_json(output / "curved-reconstruction.json", reconstruction.to_dict())

    artifacts = {
        "analysis": str(output / "analysis.json"),
        "sourceOriginal": str(original_path),
        "sourceGlb": str(output / "source.glb"),
        "repair": str(output / "repair.json"),
        "curvedPlate": str(artifact_path),
        "cadgraph": str(graph_path),
        "cadquerySource": str(output / "model.cq.py"),
        "step": str(output / "model.step"),
        "modelGlb": str(output / "reconstructed.glb"),
        "validation": str(output / "validation.json"),
        "curvedReconstruction": str(output / "curved-reconstruction.json"),
    }
    result = CurvedConversionResult(
        source=source,
        repair=repair,
        reconstruction=reconstruction,
        graph=graph,
        compilation=compilation,
        step=step,
        audit=audit,
        units=units,
        artifacts=artifacts,
    )
    _write_json(
        output / "manifest.json",
        {name: Path(path).name for name, path in sorted(artifacts.items())},
    )
    return result


__all__ = [
    "APPROXIMATE_SCOPE",
    "CURVED_ARTIFACT_ID",
    "CurvedConversionError",
    "CurvedConversionResult",
    "create_curved_conversion",
]
