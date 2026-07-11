"""Explicit, non-parametric faceted fallback with kernel-validated STEP output."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import trimesh
from mesh2param_contracts import CADGraph, canonical_json_bytes

from .compiler import CompilationResult, compile_cadgraph
from .ingest import IngestedMesh, MeshLimits, ingest_mesh
from .repair import RepairResult, repair_mesh
from .source import write_cadquery_source
from .tessellation import Tessellation, write_binary_stl, write_glb
from .units import (
    DEFAULT_FACETED_SEWING_TOLERANCE_MM,
    MAXIMUM_FACETED_SEWING_TOLERANCE_MM,
    millimeters_to_project_units,
    project_units_to_millimeters,
    validate_physical_tolerance,
)
from .validation import StepValidation, export_step_validated

FIXED_TIMESTAMP = "1970-01-01T00:00:00Z"
SOURCE_ARTIFACT_ID = "artifact.source"


class FacetedFallbackError(ValueError):
    """A fail-closed faceted conversion error with a stable code and phase."""

    def __init__(self, phase: str, code: str, message: str) -> None:
        super().__init__(message)
        self.phase = phase
        self.code = code


@dataclass(slots=True)
class FacetedFallbackResult:
    source: IngestedMesh
    repair: RepairResult
    graph: CADGraph
    compilation: CompilationResult
    step: StepValidation
    sewing_tolerance: float
    units: str
    artifacts: dict[str, str]

    @property
    def sewing_tolerance_mm(self) -> float:
        return project_units_to_millimeters(self.sewing_tolerance, self.units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "valid",
            "scope": "explicit non-parametric faceted fallback",
            "source": self.source.to_dict(),
            "repair": self.repair.to_dict(),
            "cadgraph": self.graph.model_dump(mode="json", by_alias=True),
            "compilation": self.compilation.to_dict(),
            "stepValidation": self.step.to_dict(),
            "sewingTolerance": self.sewing_tolerance,
            "sewingToleranceUnits": self.units,
            "sewingToleranceMm": self.sewing_tolerance_mm,
            "artifacts": dict(sorted(self.artifacts.items())),
            "limitations": [
                "The result is a faceted imported feature, not inferred parametric history.",
                "Open triangle boundaries are sewn only within the displayed explicit tolerance.",
                (
                    "reconstructed.glb is a preserved-source proxy, not a tessellation of the "
                    "sewn B-Rep; the STEP is independently kernel-validated."
                ),
            ],
        }


def _vector(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": x, "y": y, "z": z}


def _build_graph(
    source: IngestedMesh,
    *,
    units: str,
    sewing_tolerance: float,
    source_descriptor: Mapping[str, Any],
) -> CADGraph:
    sewing_tolerance_mm = project_units_to_millimeters(sewing_tolerance, units)
    linear_resolution = min(
        millimeters_to_project_units(0.001, units),
        sewing_tolerance,
    )
    source_document = {
        "format": source_descriptor["format"],
        "sha256": source.metadata.sha256,
        "originalFileName": source_descriptor["originalFileName"],
        "byteSize": source.metadata.byte_size,
        "triangleCount": source.diagnostics.triangle_count,
        "declaredUnits": source_descriptor["declaredUnits"],
        "scaleFactor": source_descriptor["scaleFactor"],
    }
    feature_id = "feature.faceted-source"
    topology_id = f"{feature_id}.result"
    evidence_id = "evidence.faceted-source"
    document: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "id": "reconstruction.faceted-fallback",
        "name": "Faceted fallback",
        "units": units,
        "source": source_document,
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
            "surfaceDeviation": sewing_tolerance,
            "angularDeviationDeg": 1.0,
            "linearResolution": linear_resolution,
        },
        "sketches": [],
        "features": [
            {
                "id": feature_id,
                "name": "Imported source facets",
                "operation": "importedFaceted",
                "booleanMode": "base",
                "order": 0,
                "dependencies": [],
                "suppressed": False,
                "sourceEvidence": [evidence_id],
                "confidence": 1.0,
                "userLocks": [],
                "overrides": [],
                "semanticOutputs": [topology_id],
                "sourceArtifactId": SOURCE_ARTIFACT_ID,
                "meshSha256": source.metadata.sha256,
                "intent": "fallback",
                "sewingTolerance": sewing_tolerance,
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
                "sourceType": "imported",
                "sourceIds": [],
                "residual": sewing_tolerance,
                "confidence": 1.0,
                "notes": "Original source facets with an explicit bounded OCCT sewing tolerance.",
                "metadata": {
                    "meshSha256": source.metadata.sha256,
                    "sewingTolerance": sewing_tolerance,
                    "sewingToleranceUnits": units,
                    "sewingToleranceMm": sewing_tolerance_mm,
                    "sourcePreserved": True,
                },
            }
        ],
        "userLocks": [],
        "overrides": [],
        "reconstructionSettings": {
            "maxFeatures": 1,
            "beamWidth": 1,
            "candidatesPerResidual": 1,
            "wallClockSeconds": 300.0,
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
        "deterministicSeed": 0x4D325046,
        "fitMetrics": {
            "rmsSurfaceDistance": sewing_tolerance,
            "p95SurfaceDistance": sewing_tolerance,
            "maxSurfaceDistance": sewing_tolerance,
            "normalAgreement": 0.0,
            "volumeDifference": 0.0,
            "overlap": 0.0,
            "unmatchedSourceArea": source.diagnostics.surface_area,
            "excessResultArea": source.diagnostics.surface_area,
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
            "versionId": "version.faceted-fallback.1",
            "createdAt": FIXED_TIMESTAMP,
            "createdBy": "mesh2param-faceted-fallback",
            "message": "Explicit non-parametric faceted fallback from the preserved source mesh.",
        },
        "extensions": {
            "mesh2param.dev/facetedFallback": {
                "nonParametric": True,
                "sourcePreserved": True,
                "sewingTolerance": sewing_tolerance,
                "sewingToleranceUnits": units,
                "sewingToleranceMm": sewing_tolerance_mm,
                "fitMetricMethod": "conservative sewing-tolerance bound",
                "sourceVolumeComparison": "not-applicable-open-source-mesh",
                "browserTessellation": "preserved-source-proxy",
                "browserTessellationRepresentsKernelResult": False,
            }
        },
    }
    return CADGraph.model_validate(document)


def _validated_graph(graph: CADGraph, step: StepValidation) -> CADGraph:
    document = graph.model_dump(mode="json", by_alias=True)
    document["fitMetrics"]["volumeDifference"] = abs(step.source.volume)
    document["validation"] = {
        "status": "partial" if step.valid else "invalid",
        "brepValid": step.source.valid,
        "stepReimportValid": step.reimport.valid,
        "toleranceSatisfied": None,
        "checkedAt": FIXED_TIMESTAMP,
        "lastValidFeatureId": "feature.faceted-source",
        "issues": [
            {
                "code": "faceted-fallback",
                "message": (
                    "This kernel-valid STEP is a non-parametric faceted fallback; no analytic "
                    "history or measured source-to-result deviation is claimed."
                ),
                "severity": "warning",
                "featureId": "feature.faceted-source",
            }
        ],
    }
    return CADGraph.model_validate(document)


def _mesh_tessellation(mesh: Any) -> Tessellation:
    vertices = cast(
        tuple[tuple[float, float, float], ...],
        tuple(tuple(float(value) for value in vertex) for vertex in mesh.vertices),
    )
    triangles = cast(
        tuple[tuple[int, int, int], ...],
        tuple(tuple(int(value) for value in face) for face in mesh.faces),
    )
    return Tessellation(
        vertices,
        triangles,
        (),
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _manifest(output: Path, artifacts: dict[str, str]) -> None:
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
    _write_json(
        output / "manifest.json",
        {
            "schemaVersion": "1.0.0",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "scope": "faceted-fallback",
            "artifacts": records,
        },
    )


def create_faceted_fallback(
    source_path: str | Path,
    output_directory: str | Path,
    *,
    units: str = "mm",
    sewing_tolerance: float | None = None,
    source_descriptor: Mapping[str, Any] | None = None,
    mesh_limits: MeshLimits | None = None,
) -> FacetedFallbackResult:
    """Create a source-bound faceted solid and prove its STEP round trip.

    ``sewing_tolerance`` is expressed in ``units``. Engine artifacts record both the project-unit
    value and its physical millimeter value.
    """

    requested_tolerance = sewing_tolerance
    if requested_tolerance is None:
        try:
            requested_tolerance = millimeters_to_project_units(
                DEFAULT_FACETED_SEWING_TOLERANCE_MM,
                units,
            )
        except ValueError as exc:
            raise FacetedFallbackError(
                "sewing facets",
                "invalid_sewing_tolerance",
                str(exc),
            ) from exc
    try:
        project_tolerance = validate_physical_tolerance(
            requested_tolerance,
            units,
            maximum_mm=MAXIMUM_FACETED_SEWING_TOLERANCE_MM,
        )
    except (TypeError, ValueError) as exc:
        raise FacetedFallbackError(
            "sewing facets",
            "invalid_sewing_tolerance",
            str(exc),
        ) from exc
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    source = ingest_mesh(source_path, limits=mesh_limits or MeshLimits())
    if source.metadata.format != "stl":
        raise FacetedFallbackError(
            "validating upload",
            "unsupported_faceted_format",
            "The explicit faceted STEP fallback currently supports STL sources only.",
        )
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
        raise FacetedFallbackError(
            "validating upload",
            "faceted_source_metadata_mismatch",
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
        raise FacetedFallbackError(
            "normalizing source units",
            "faceted_source_transform_unsupported",
            (
                "Faceted STEP fallback currently requires source units to match project units "
                "and a scale factor of 1. Normalize a working copy before retrying; the original "
                "upload will remain unchanged."
            ),
        )
    normalized_source_descriptor: dict[str, Any] = {
        "format": source.metadata.format,
        "sha256": source.metadata.sha256,
        "originalFileName": original_file_name,
        "declaredUnits": declared_units,
        "scaleFactor": float(scale_factor),
    }

    original_path = output / "source.original.stl"
    original_path.write_bytes(source.original_bytes)
    repair = repair_mesh(source, limits=mesh_limits or MeshLimits())
    _write_json(output / "analysis.json", source.to_dict())
    _write_json(output / "repair.json", repair.to_dict())
    write_glb(_mesh_tessellation(source.mesh), output / "source.glb")
    write_binary_stl(_mesh_tessellation(repair.mesh), output / "repaired.stl")
    write_glb(_mesh_tessellation(repair.mesh), output / "repaired.glb")
    # The faceted OCCT result is intentionally not re-tessellated for this large-model fallback.
    # Keep the conventional artifact name for viewer compatibility, but make its content and
    # metadata explicitly a preserved-source proxy.
    write_glb(_mesh_tessellation(source.mesh), output / "reconstructed.glb")

    graph = _build_graph(
        source,
        units=units,
        sewing_tolerance=project_tolerance,
        source_descriptor=normalized_source_descriptor,
    )
    resolver = {SOURCE_ARTIFACT_ID: original_path}
    compilation = compile_cadgraph(graph, artifact_resolver=resolver)
    if not compilation.success:
        error = compilation.errors[0] if compilation.errors else None
        raise FacetedFallbackError(
            "sewing facets",
            error.code if error is not None else "faceted_compile_failed",
            error.kernel_error if error is not None else "OCCT rejected the faceted source.",
        )
    shape = compilation.require_shape()
    try:
        step = export_step_validated(
            shape,
            output / "model.step",
            units=units,
            linear_resolution=graph.project_tolerance.linear_resolution,
            require_tessellation=False,
        )
    except ValueError as exc:
        raise FacetedFallbackError(
            "reimporting STEP",
            "faceted_step_validation_failed",
            str(exc),
        ) from exc
    graph = _validated_graph(graph, step)
    graph_path = output / "model.cadgraph.json"
    graph_path.write_bytes(canonical_json_bytes(graph))
    write_cadquery_source(
        graph,
        output / "model.cq.py",
        artifact_paths={SOURCE_ARTIFACT_ID: "source.original.stl"},
    )
    validation = {
        "status": "partial",
        "brepValid": step.source.valid,
        "stepReimportValid": step.reimport.valid,
        "toleranceSatisfied": None,
        "step": step.to_dict(),
        "compilation": compilation.to_dict(),
        "facetedFallback": {
            "nonParametric": True,
            "sewingTolerance": project_tolerance,
            "sewingToleranceUnits": units,
            "sewingToleranceMm": project_units_to_millimeters(project_tolerance, units),
            "sourcePreserved": True,
            "geometricDeviationMeasured": False,
            "browserTessellation": "preserved-source-proxy",
            "browserTessellationRepresentsKernelResult": False,
        },
    }
    _write_json(output / "validation.json", validation)
    artifacts = {
        "analysis": str(output / "analysis.json"),
        "sourceOriginal": str(original_path),
        "sourceGlb": str(output / "source.glb"),
        "repair": str(output / "repair.json"),
        "repairedMesh": str(output / "repaired.stl"),
        "repairedGlb": str(output / "repaired.glb"),
        "cadgraph": str(graph_path),
        "cadquerySource": str(output / "model.cq.py"),
        "step": str(output / "model.step"),
        "modelGlb": str(output / "reconstructed.glb"),
        "validation": str(output / "validation.json"),
    }
    result = FacetedFallbackResult(
        source,
        repair,
        graph,
        compilation,
        step,
        project_tolerance,
        units,
        artifacts,
    )
    _write_json(output / "faceted-fallback.json", result.to_dict())
    artifacts["facetedFallback"] = str(output / "faceted-fallback.json")
    _manifest(output, artifacts)
    return result


__all__ = [
    "SOURCE_ARTIFACT_ID",
    "FacetedFallbackError",
    "FacetedFallbackResult",
    "create_faceted_fallback",
]
