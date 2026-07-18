"""Evidence-driven feature inference and bounded candidate scoring."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import cadquery as cq
import numpy as np
import trimesh
from mesh2param_contracts import CADGraph

from .compiler import CompilationResult, compile_cadgraph
from .frame import CoordinateFrame
from .prismatic import ArcPrimitive, BSplineSegment, CirclePrimitive, ExtrusionCandidate
from .segmentation import SurfacePatch
from .sketches import InferredProfile


@dataclass(frozen=True, slots=True)
class Measurement:
    measured: float
    suggested_nominal: float | None
    delta: float | None
    nominal_accepted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "measured": self.measured,
            "suggestedNominal": self.suggested_nominal,
            "delta": self.delta,
            "nominalAccepted": self.nominal_accepted,
        }


def measure(
    value: float,
    *,
    snap_grid: float = 0.5,
    snap_tolerance: float = 0.05,
) -> Measurement:
    if not math.isfinite(value):
        raise ValueError("measurement must be finite")
    nominal = round(value / snap_grid) * snap_grid
    delta = nominal - value
    if abs(delta) > snap_tolerance:
        return Measurement(value, None, None)
    return Measurement(value, float(nominal), float(delta))


def nominal_preview(measurement: Measurement) -> float:
    return (
        measurement.suggested_nominal
        if measurement.suggested_nominal is not None
        else measurement.measured
    )


@dataclass(frozen=True, slots=True)
class InferredHole:
    patch_id: str
    position_mm: tuple[float, float, float]
    axis: tuple[float, float, float]
    diameter_mm: float
    depth_mm: float
    confidence: float
    residual_p95_mm: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "patchId": self.patch_id,
            "positionMm": [measure(value).to_dict() for value in self.position_mm],
            "axis": list(self.axis),
            "diameterMm": measure(self.diameter_mm).to_dict(),
            "depthMm": measure(self.depth_mm).to_dict(),
            "confidence": self.confidence,
            "residualP95Mm": self.residual_p95_mm,
        }


def infer_through_holes(
    mesh: trimesh.Trimesh,
    patches: tuple[SurfacePatch, ...] | list[SurfacePatch],
    frame: CoordinateFrame,
) -> tuple[InferredHole, ...]:
    local_vertices = frame.world_to_local(np.asarray(mesh.vertices, dtype=np.float64))
    holes: list[InferredHole] = []
    for patch in patches:
        if (
            patch.kind != "cylinder"
            or patch.cylinder_axis is None
            or patch.cylinder_axis_point is None
            or patch.cylinder_radius_mm is None
        ):
            continue
        local_axis = frame.axes.T @ np.asarray(patch.cylinder_axis)
        axis_dimension = int(np.argmax(np.abs(local_axis)))
        if abs(float(local_axis[axis_dimension])) < 0.995:
            continue
        # Automatic X-axis cylinders are outside the current L-bracket claim.
        if axis_dimension == 0:
            continue
        point = frame.world_to_local(np.asarray((patch.cylinder_axis_point,)))[0]
        patch_vertices = local_vertices[list(patch.vertex_ids)]
        axial_min = float(np.min(patch_vertices[:, axis_dimension]))
        axial_max = float(np.max(patch_vertices[:, axis_dimension]))
        position = point.copy()
        position[axis_dimension] = axial_max
        axis = np.zeros(3)
        axis[axis_dimension] = -1.0
        holes.append(
            InferredHole(
                patch_id=patch.id,
                position_mm=(float(position[0]), float(position[1]), float(position[2])),
                axis=(float(axis[0]), float(axis[1]), float(axis[2])),
                diameter_mm=2 * patch.cylinder_radius_mm,
                depth_mm=axial_max - axial_min,
                confidence=patch.confidence,
                residual_p95_mm=patch.residuals_mm.p95,
            )
        )
    holes.sort(key=lambda hole: (-int(np.argmax(np.abs(hole.axis))), hole.position_mm[0]))
    return tuple(holes)


def _vector3(values: Sequence[float]) -> dict[str, float]:
    return {"x": float(values[0]), "y": float(values[1]), "z": float(values[2])}


def _vector2(values: Sequence[float]) -> dict[str, float]:
    return {"x": float(values[0]), "y": float(values[1])}


def _measurement_metadata(value: float) -> dict[str, Any]:
    return measure(value).to_dict()


def build_l_bracket_cadgraph(
    *,
    source: Mapping[str, Any],
    frame: CoordinateFrame,
    profile: InferredProfile,
    holes: tuple[InferredHole, ...],
    use_nominal_preview: bool = False,
    deterministic_seed: int = 0x4D325006,
) -> CADGraph:
    """Create one schema-valid editable graph from supported L-bracket evidence."""

    if len(holes) != 4:
        raise ValueError(
            f"supported L-bracket inference requires four cylinders; found {len(holes)}"
        )

    def selected(value: float) -> float:
        measurement = measure(value)
        return nominal_preview(measurement) if use_nominal_preview else measurement.measured

    profile_points = [
        (selected(y_value), selected(z_value)) for y_value, z_value in profile.points_yz_mm
    ]
    profile_evidence_id = "evidence.profile"
    evidence: list[dict[str, Any]] = [
        {
            "id": "evidence.frame",
            "sourceType": "derived",
            "sourceIds": list(frame.chosen.support_patch_ids),
            "confidence": float(frame.confidence),
            "notes": "Dominant plane-normal triad; alternatives preserved in extension data.",
            "metadata": {
                "extentsMm": list(frame.extents_mm),
                "alternatives": [candidate.to_dict() for candidate in frame.alternatives],
            },
        },
        {
            "id": profile_evidence_id,
            "sourceType": "meshPatch",
            "sourceIds": list(profile.evidence_ids),
            "confidence": float(profile.confidence),
            "notes": "Two matched six-line end loops support one base extrusion.",
            "metadata": {
                "profileYZ": [
                    [_measurement_metadata(y_value), _measurement_metadata(z_value)]
                    for y_value, z_value in profile.points_yz_mm
                ],
                "extrusionDistanceMm": _measurement_metadata(profile.extrusion_distance_mm),
            },
        },
    ]
    features: list[dict[str, Any]] = [
        {
            "id": "feature.base",
            "name": "Recovered L-profile extrusion",
            "operation": "extrusion",
            "booleanMode": "base",
            "order": 0,
            "dependencies": [],
            "suppressed": False,
            "sourceEvidence": [profile_evidence_id],
            "confidence": float(profile.confidence),
            "userLocks": [],
            "overrides": [],
            "semanticOutputs": ["feature.base.result"],
            "sketchId": "sketch.base",
            "profileIds": ["sketch.base.profile"],
            "direction": _vector3((1.0, 0.0, 0.0)),
            "extent": "blind",
            "distance": selected(profile.extrusion_distance_mm),
        }
    ]
    for index, hole in enumerate(holes, start=1):
        evidence_id = f"evidence.hole.{index}"
        evidence.append(
            {
                "id": evidence_id,
                "sourceType": "meshPatch",
                "sourceIds": [hole.patch_id],
                "measuredValue": float(hole.diameter_mm),
                "suggestedNominalValue": measure(hole.diameter_mm).suggested_nominal,
                "residual": float(hole.residual_p95_mm),
                "confidence": float(hole.confidence),
                "notes": (
                    "Full-coverage cylinder supports a through-hole; snapping is preview-only."
                ),
                "metadata": {
                    "positionMm": [_measurement_metadata(value) for value in hole.position_mm],
                    "axis": list(hole.axis),
                    "depthMm": _measurement_metadata(hole.depth_mm),
                    "nominalAccepted": False,
                },
            }
        )
        features.append(
            {
                "id": f"feature.hole.{index}",
                "name": f"Recovered through hole {index}",
                "operation": "hole",
                "booleanMode": "subtractive",
                "order": index,
                "dependencies": [features[-1]["id"]],
                "suppressed": False,
                "sourceEvidence": [evidence_id],
                "confidence": float(hole.confidence),
                "userLocks": [],
                "overrides": [],
                "semanticOutputs": [f"feature.hole.{index}.result"],
                "holeType": "through",
                "position": _vector3(tuple(selected(value) for value in hole.position_mm)),
                "axis": _vector3(hole.axis),
                "diameter": selected(hole.diameter_mm),
            }
        )
    semantic_topology = [
        {
            "id": f"{feature['id']}.result",
            "kind": "solid",
            "producerFeatureId": feature["id"],
            "role": "resultSolid",
            "generatedFrom": list(feature.get("profileIds", feature["sourceEvidence"])),
            "status": "unresolved",
        }
        for feature in features
    ]
    source_sha = str(source["sha256"])
    document: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "id": "reconstruction.l-bracket",
        "name": "Recovered L-bracket candidate",
        "units": str(source.get("units", "mm")),
        "source": {
            "format": str(source["format"]),
            "sha256": source_sha,
            "originalFileName": str(source["originalFileName"]),
            "byteSize": int(source["byteSize"]),
            "triangleCount": int(source["triangleCount"]),
            "declaredUnits": str(source.get("units", "mm")),
            "scaleFactor": float(source.get("scaleFactor", 1.0)),
        },
        "sourceCoordinateFrame": {
            "origin": _vector3(frame.origin),
            "xAxis": _vector3(frame.x_axis),
            "yAxis": _vector3(frame.y_axis),
            "zAxis": _vector3(frame.z_axis),
            "locked": False,
            "confidence": float(frame.confidence),
            "evidenceIds": ["evidence.frame"],
        },
        "projectTolerance": {
            "surfaceDeviation": 0.1,
            "angularDeviationDeg": 1.0,
            "linearResolution": 0.001,
        },
        "sketches": [
            {
                "id": "sketch.base",
                "name": "Recovered L profile",
                "plane": {
                    "origin": _vector3((0.0, 0.0, 0.0)),
                    "normal": _vector3((1.0, 0.0, 0.0)),
                    "xAxis": _vector3((0.0, 1.0, 0.0)),
                },
                "entities": [
                    {
                        "id": "sketch.base.polyline",
                        "kind": "polyline",
                        "construction": False,
                        "points": [
                            {"x": float(y_value), "y": float(z_value)}
                            for y_value, z_value in profile_points
                        ],
                        "closed": True,
                        "sourceEvidence": [profile_evidence_id],
                        "confidence": float(profile.confidence),
                        "locked": False,
                        "suppressed": False,
                    }
                ],
                "constraints": [],
                "profiles": [
                    {
                        "id": "sketch.base.profile",
                        "name": "Recovered L profile",
                        "outerLoop": ["sketch.base.polyline"],
                        "innerLoops": [],
                        "orientation": "counterclockwise",
                        "closed": True,
                        "sourceEvidence": [profile_evidence_id],
                        "confidence": float(profile.confidence),
                        "locked": False,
                    }
                ],
                "sourceEvidence": [profile_evidence_id],
                "confidence": float(profile.confidence),
                "userLocks": [],
                "overrides": [],
                "suppressed": False,
            }
        ],
        "features": features,
        "semanticTopology": semantic_topology,
        "sourceEvidence": evidence,
        "userLocks": [],
        "overrides": [],
        "reconstructionSettings": {
            "maxFeatures": 16,
            "beamWidth": 2,
            "candidatesPerResidual": 2,
            "wallClockSeconds": 120.0,
            "maxRebuilds": 8,
            "minScoreImprovement": 0.0001,
            "nominalSnappingEnabled": True,
            "nominalSnapTolerance": 0.05,
            "scoreWeights": {
                "rmsDistance": 1.0,
                "p95Distance": 1.0,
                "maxDistance": 0.5,
                "normalAgreement": 0.5,
                "volumeDifference": 0.75,
                "overlap": 0.75,
                "sharpEdgeAlignment": 0.5,
                "boundaryAlignment": 0.5,
                "unmatchedSource": 1.0,
                "excessResult": 1.0,
                "complexity": 0.1,
                "unsupportedOperation": 2.0,
                "evidenceConfidence": 0.25,
            },
        },
        "engineVersions": {
            "mesh2param": "0.1.0",
            "contracts": "1.0.0",
            "cadBackend": "OCCT",
            "cadQuery": "2.8.0",
            "ocp": "7.9.3.1.1",
            "dependencies": {"numpy": np.__version__, "trimesh": trimesh.__version__},
        },
        "deterministicSeed": deterministic_seed,
        "fitMetrics": {
            "rmsSurfaceDistance": 0.0,
            "p95SurfaceDistance": 0.0,
            "maxSurfaceDistance": 0.0,
            "normalAgreement": 0.0,
            "volumeDifference": 0.0,
            "overlap": 0.0,
            "unmatchedSourceArea": 0.0,
            "excessResultArea": 0.0,
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
            "versionId": "version.reconstruction.1",
            "createdAt": "1970-01-01T00:00:00Z",
            "createdBy": "mesh2param-reconstruction",
            "message": "Measured L-bracket candidate; nominal suggestions remain unaccepted.",
        },
        "extensions": {
            "mesh2param.dev/reconstruction": {
                "scope": "plane-cylinder L-bracket",
                "candidate": "nominal-preview" if use_nominal_preview else "measured",
                "frameAlternatives": [candidate.to_dict() for candidate in frame.alternatives],
                "limitations": [
                    "X polarity may be tied for symmetric brackets.",
                    "No automatic fillet, chamfer, pattern, or damaged-boundary inference.",
                ],
            }
        },
    }
    return CADGraph.model_validate(document)


def build_prismatic_cadgraph(
    *,
    source: Mapping[str, Any],
    candidate: ExtrusionCandidate,
    deterministic_seed: int = 0x4D325006,
) -> CADGraph:
    """Build an editable extrusion, with an explicit polygon cut when recovered."""

    if (
        not candidate.accepted
        or candidate.frame is None
        or candidate.axis is None
        or candidate.distance_mm is None
        or candidate.cap_patch_ids is None
        or not candidate.profiles
    ):
        raise ValueError("prismatic CADGraph requires a fully validated extrusion candidate")
    frame = candidate.frame
    evidence_id = "evidence.prismatic-profile"
    spline_mode = any(
        isinstance(primitive, BSplineSegment)
        for profile in candidate.profiles
        for primitive in profile
    )
    polygon_hypotheses = [
        item for item in candidate.polygon_hypotheses if item is not None
    ]
    polygon = polygon_hypotheses[0] if polygon_hypotheses else None
    if spline_mode and (len(candidate.profiles) != 2 or len(polygon_hypotheses) != 1):
        raise ValueError(
            "spline-prismatic CADGraph requires exactly one regular-polygon cut hypothesis"
        )
    entities: list[dict[str, Any]] = []
    loop_ids: list[list[str]] = []
    primitive_index = 0
    base_profiles = candidate.profiles[:1] if spline_mode else candidate.profiles
    for profile in base_profiles:
        identifiers: list[str] = []
        for primitive in profile:
            primitive_index += 1
            identifier = f"sketch.base.entity.{primitive_index:03d}"
            identifiers.append(identifier)
            common = {
                "id": identifier,
                "construction": False,
                "sourceEvidence": [evidence_id],
                "confidence": float(candidate.confidence),
                "locked": False,
                "suppressed": False,
            }
            if isinstance(primitive, CirclePrimitive):
                entities.append(
                    {
                        **common,
                        "kind": "circle",
                        "center": _vector2(primitive.center),
                        "radius": float(primitive.radius_mm),
                    }
                )
            elif isinstance(primitive, ArcPrimitive):
                start_angle = math.degrees(
                    math.atan2(
                        primitive.start[1] - primitive.center[1],
                        primitive.start[0] - primitive.center[0],
                    )
                )
                entities.append(
                    {
                        **common,
                        "kind": "circularArc",
                        "center": _vector2(primitive.center),
                        "radius": float(primitive.radius_mm),
                        "startAngleDeg": start_angle,
                        "endAngleDeg": start_angle + primitive.sweep_deg,
                        "clockwise": primitive.clockwise,
                    }
                )
            elif isinstance(primitive, BSplineSegment):
                entities.append(
                    {
                        **common,
                        "kind": "bspline",
                        "degree": primitive.degree,
                        "controlPoints": [
                            _vector2(point) for point in primitive.control_points
                        ],
                        "clamped": True,
                        "rational": False,
                        "periodic": False,
                    }
                )
            else:
                entities.append(
                    {
                        **common,
                        "kind": "line",
                        "start": _vector2(primitive.start),
                        "end": _vector2(primitive.end),
                    }
                )
        loop_ids.append(identifiers)
    entities.append(
        {
            "id": "sketch.base.closed-profile",
            "kind": "closedProfile",
            "construction": False,
            "outerLoop": loop_ids[0],
            "innerLoops": loop_ids[1:],
            "orientation": "counterclockwise",
            "sourceEvidence": [evidence_id],
            "confidence": float(candidate.confidence),
            "locked": False,
            "suppressed": False,
        }
    )
    source_sha = str(source["sha256"])
    origin = frame.origin
    axis = candidate.axis
    sketches: list[dict[str, Any]] = [
        {
            "id": "sketch.base",
            "name": (
                "Recovered spline-aware profile"
                if spline_mode
                else "Recovered line and arc profile"
            ),
            "plane": {
                "origin": _vector3(origin),
                "normal": _vector3(axis),
                "xAxis": _vector3(frame.u),
            },
            "entities": entities,
            "constraints": [],
            "profiles": [
                {
                    "id": "sketch.base.profile",
                    "name": "Recovered closed profile",
                    "outerLoop": loop_ids[0],
                    "innerLoops": [] if spline_mode else loop_ids[1:],
                    "orientation": "counterclockwise",
                    "closed": True,
                    "sourceEvidence": [evidence_id],
                    "confidence": float(candidate.confidence),
                    "locked": False,
                }
            ],
            "sourceEvidence": [evidence_id],
            "confidence": float(candidate.confidence),
            "userLocks": [],
            "overrides": [],
            "suppressed": False,
        }
    ]
    features: list[dict[str, Any]] = [
        {
            "id": "feature.base",
            "name": "Recovered analytic extrusion",
            "operation": "extrusion",
            "booleanMode": "base",
            "order": 0,
            "dependencies": [],
            "suppressed": False,
            "sourceEvidence": [evidence_id],
            "confidence": float(candidate.confidence),
            "userLocks": [],
            "overrides": [],
            "semanticOutputs": ["feature.base.result"],
            "sketchId": "sketch.base",
            "profileIds": ["sketch.base.profile"],
            "direction": _vector3(axis),
            "extent": "blind",
            "distance": float(candidate.distance_mm),
        }
    ]
    semantic_topology: list[dict[str, Any]] = [
        {
            "id": "feature.base.result",
            "kind": "solid",
            "producerFeatureId": "feature.base",
            "role": "intermediateSolid" if spline_mode else "resultSolid",
            "generatedFrom": ["sketch.base.profile"],
            "status": "unresolved",
        }
    ]
    if spline_mode and polygon is not None:
        cut_ids = [f"sketch.hex-cut.entity.{index + 1:03d}" for index in range(polygon.side_count)]
        cut_entities: list[dict[str, Any]] = []
        for index, (start, end) in enumerate(
            zip(polygon.points, (*polygon.points[1:], polygon.points[0]), strict=True)
        ):
            cut_entities.append(
                {
                    "id": cut_ids[index],
                    "kind": "line",
                    "construction": False,
                    "start": _vector2(start),
                    "end": _vector2(end),
                    "sourceEvidence": [evidence_id],
                    "confidence": float(candidate.confidence),
                    "locked": False,
                    "suppressed": False,
                }
            )
        cut_entities.append(
            {
                "id": "sketch.hex-cut.closed-profile",
                "kind": "closedProfile",
                "construction": False,
                "outerLoop": cut_ids,
                "innerLoops": [],
                "orientation": "clockwise" if polygon.clockwise else "counterclockwise",
                "sourceEvidence": [evidence_id],
                "confidence": float(candidate.confidence),
                "locked": False,
                "suppressed": False,
            }
        )
        sketches.append(
            {
                "id": "sketch.hex-cut",
                "name": f"Recovered regular {polygon.side_count}-sided cut",
                "plane": {
                    "origin": _vector3(origin),
                    "normal": _vector3(axis),
                    "xAxis": _vector3(frame.u),
                },
                "entities": cut_entities,
                "constraints": [],
                "profiles": [
                    {
                        "id": "sketch.hex-cut.profile",
                        "name": "Recovered regular polygon",
                        "outerLoop": cut_ids,
                        "innerLoops": [],
                        "orientation": "clockwise" if polygon.clockwise else "counterclockwise",
                        "closed": True,
                        "sourceEvidence": [evidence_id],
                        "confidence": float(candidate.confidence),
                        "locked": False,
                    }
                ],
                "sourceEvidence": [evidence_id],
                "confidence": float(candidate.confidence),
                "userLocks": [],
                "overrides": [],
                "suppressed": False,
            }
        )
        features.append(
            {
                "id": "feature.hex-cut",
                "name": f"Recovered {polygon.side_count}-sided through cut",
                "operation": "extrusion",
                "booleanMode": "subtractive",
                "order": 1,
                "dependencies": ["feature.base"],
                "suppressed": False,
                "sourceEvidence": [evidence_id],
                "confidence": float(candidate.confidence),
                "userLocks": [],
                "overrides": [],
                "semanticOutputs": ["feature.hex-cut.result"],
                "sketchId": "sketch.hex-cut",
                "profileIds": ["sketch.hex-cut.profile"],
                "direction": _vector3(axis),
                "extent": "throughAll",
                "distance": None,
            }
        )
        semantic_topology.append(
            {
                "id": "feature.hex-cut.result",
                "kind": "solid",
                "producerFeatureId": "feature.hex-cut",
                "role": "resultSolid",
                "generatedFrom": ["sketch.hex-cut.profile"],
                "status": "unresolved",
            }
        )
    document: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "id": "reconstruction.prismatic",
        "name": "Recovered analytic extrusion",
        "units": str(source.get("units", "mm")),
        "source": {
            "format": str(source["format"]),
            "sha256": source_sha,
            "originalFileName": str(source["originalFileName"]),
            "byteSize": int(source["byteSize"]),
            "triangleCount": int(source["triangleCount"]),
            "declaredUnits": str(source.get("units", "mm")),
            "scaleFactor": float(source.get("scaleFactor", 1.0)),
        },
        "sourceCoordinateFrame": {
            "origin": _vector3(origin),
            "xAxis": _vector3(frame.u),
            "yAxis": _vector3(frame.v),
            "zAxis": _vector3(frame.w),
            "locked": False,
            "confidence": float(candidate.confidence),
            "evidenceIds": [evidence_id],
        },
        "projectTolerance": {
            "surfaceDeviation": 0.05,
            "angularDeviationDeg": 1.0,
            "linearResolution": 0.001,
        },
        "sketches": sketches,
        "features": features,
        "semanticTopology": semantic_topology,
        "sourceEvidence": [
            {
                "id": evidence_id,
                "sourceType": "meshPatch",
                "sourceIds": list(candidate.cap_patch_ids),
                "measuredValue": float(candidate.distance_mm),
                "residual": float(candidate.side_normal_rms or 0.0),
                "confidence": float(candidate.confidence),
                "notes": (
                    "Matched opposing caps and perpendicular side normals support one "
                    "linear extrusion."
                ),
                "metadata": {
                    "axis": list(axis),
                    "capOffsetsMm": list(candidate.cap_offsets_mm or ()),
                    "profileLoopCount": len(candidate.profiles),
                    "primitiveCount": sum(len(profile) for profile in candidate.profiles),
                    "diagnostics": [item.to_dict() for item in candidate.diagnostics],
                },
            }
        ],
        "userLocks": [],
        "overrides": [],
        "reconstructionSettings": {
            "maxFeatures": 16,
            "beamWidth": 2,
            "candidatesPerResidual": 2,
            "wallClockSeconds": 120.0,
            "maxRebuilds": 8,
            "minScoreImprovement": 0.0001,
            "nominalSnappingEnabled": True,
            "nominalSnapTolerance": 0.05,
            "scoreWeights": {
                "rmsDistance": 1.0,
                "p95Distance": 1.0,
                "maxDistance": 0.5,
                "normalAgreement": 0.5,
                "volumeDifference": 0.75,
                "overlap": 0.75,
                "sharpEdgeAlignment": 0.5,
                "boundaryAlignment": 0.5,
                "unmatchedSource": 1.0,
                "excessResult": 1.0,
                "complexity": 0.1,
                "unsupportedOperation": 2.0,
                "evidenceConfidence": 0.25,
            },
        },
        "engineVersions": {
            "mesh2param": "0.1.0",
            "contracts": "1.0.0",
            "cadBackend": "OCCT",
            "cadQuery": "2.8.0",
            "ocp": "7.9.3.1.1",
            "dependencies": {"numpy": np.__version__, "trimesh": trimesh.__version__},
        },
        "deterministicSeed": deterministic_seed,
        "fitMetrics": {
            "rmsSurfaceDistance": 0.0,
            "p95SurfaceDistance": 0.0,
            "maxSurfaceDistance": 0.0,
            "normalAgreement": 0.0,
            "volumeDifference": 0.0,
            "overlap": 0.0,
            "unmatchedSourceArea": 0.0,
            "excessResultArea": 0.0,
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
            "versionId": "version.reconstruction.prismatic.1",
            "createdAt": "1970-01-01T00:00:00Z",
            "createdBy": "mesh2param-reconstruction",
            "message": "Analytic prismatic profile reconstructed from extrusion evidence.",
        },
        "extensions": {
            "mesh2param.dev/prismaticReconstruction": {
                "scope": (
                    "validated linear extrusion with one bounded B-spline and polygon cut"
                    if spline_mode
                    else "validated linear extrusion of line/circular-arc profiles"
                ),
                "capPatchIds": list(candidate.cap_patch_ids),
                "distanceMeasurement": (
                    candidate.distance_measurement.to_dict()
                    if candidate.distance_measurement is not None
                    else None
                ),
                "polygonHypothesis": polygon.to_dict() if polygon is not None else None,
            }
        },
    }
    return CADGraph.model_validate(document)


@dataclass(frozen=True, slots=True)
class CandidateSearchSettings:
    beam_width: int = 2
    maximum_rebuilds: int = 8
    maximum_features: int = 16
    minimum_score_improvement: float = 0.0001


@dataclass(slots=True)
class CandidateEvaluation:
    label: str
    graph: CADGraph
    compilation: CompilationResult
    shape: cq.Shape | None
    comparison: Any | None
    score: float
    valid: bool
    rejection_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "score": self.score,
            "valid": self.valid,
            "rejectionReason": self.rejection_reason,
            "featureCount": len(self.graph.features),
            "cadgraph": self.graph.model_dump(mode="json", by_alias=True),
            "kernel": self.compilation.to_dict(),
            "comparison": self.comparison.to_dict() if self.comparison is not None else None,
        }


def compile_candidate(label: str, graph: CADGraph) -> CandidateEvaluation:
    if len(graph.features) > graph.reconstruction_settings.max_features:
        raise ValueError("candidate exceeds graph feature limit")
    compilation = compile_cadgraph(graph)
    if not compilation.success:
        return CandidateEvaluation(
            label,
            graph,
            compilation,
            compilation.shape,
            None,
            -math.inf,
            False,
            "kernel-invalid candidate rejected",
        )
    return CandidateEvaluation(
        label,
        graph,
        compilation,
        compilation.require_shape(),
        None,
        -math.inf,
        True,
        None,
    )


def score_candidate(evaluation: CandidateEvaluation, comparison: Any) -> CandidateEvaluation:
    if not evaluation.valid or evaluation.shape is None:
        return evaluation
    tolerance = float(evaluation.graph.project_tolerance.surface_deviation)
    rms = float(comparison.rms_distance_mm)
    p95 = float(comparison.p95_distance_mm)
    maximum = float(comparison.maximum_distance_mm)
    relative_volume = float(comparison.relative_volume_delta)
    coverage = float(comparison.tolerance_surface_coverage)
    normal = float(comparison.mean_normal_agreement)
    complexity = len(evaluation.graph.features) / max(
        1, evaluation.graph.reconstruction_settings.max_features
    )
    penalty = (
        min(rms / tolerance, 10.0)
        + min(p95 / tolerance, 10.0)
        + 0.5 * min(maximum / tolerance, 10.0)
        + 0.75 * min(relative_volume, 1.0)
        + (1.0 - coverage)
        + 0.5 * (1.0 - normal)
        + 0.1 * complexity
    )
    evaluation.comparison = comparison
    evaluation.score = 1.0 - penalty
    return evaluation


def select_bounded_candidates(
    candidates: Sequence[CandidateEvaluation],
    settings: CandidateSearchSettings | None = None,
) -> tuple[CandidateEvaluation, ...]:
    settings = settings or CandidateSearchSettings()
    if len(candidates) > settings.maximum_rebuilds:
        raise ValueError("candidate generation exceeded the rebuild bound")
    valid = [
        candidate for candidate in candidates if candidate.valid and candidate.shape is not None
    ]
    valid.sort(
        key=lambda candidate: (-candidate.score, len(candidate.graph.features), candidate.label)
    )
    return tuple(valid[: settings.beam_width])


__all__ = [
    "CandidateEvaluation",
    "CandidateSearchSettings",
    "InferredHole",
    "Measurement",
    "build_l_bracket_cadgraph",
    "build_prismatic_cadgraph",
    "compile_candidate",
    "infer_through_holes",
    "measure",
    "nominal_preview",
    "score_candidate",
    "select_bounded_candidates",
]
