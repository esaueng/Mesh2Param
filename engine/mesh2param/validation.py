"""B-Rep and STEP round-trip validation gates."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GeomAbs import (
    GeomAbs_BezierSurface,
    GeomAbs_BSplineSurface,
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_OffsetSurface,
    GeomAbs_OtherSurface,
    GeomAbs_Plane,
    GeomAbs_Sphere,
    GeomAbs_SurfaceOfExtrusion,
    GeomAbs_SurfaceOfRevolution,
    GeomAbs_Torus,
)

STEP_UNITS: dict[str, str] = {
    "mm": "MM",
    "cm": "CM",
    "m": "M",
    "in": "INCH",
    "ft": "FT",
}

PARAMETRIC_SURFACE_TYPES: tuple[str, ...] = (
    "plane",
    "cylinder",
    "cone",
    "sphere",
    "torus",
    "bspline",
    "bezier",
    "surfaceOfExtrusion",
    "surfaceOfRevolution",
    "offset",
    "other",
)
FREEFORM_STEP_SURFACE_TYPES: frozenset[str] = frozenset(
    {
        "bspline",
        "bezier",
        "surfaceOfExtrusion",
        "surfaceOfRevolution",
        "offset",
        "other",
    }
)


@dataclass(frozen=True, slots=True)
class ParametricSurfacePolicy:
    """Declared surface vocabulary and anti-faceting bound for one candidate."""

    allowed_surface_types: tuple[str, ...]
    source_triangle_count: int

    def validate(self) -> None:
        if self.source_triangle_count < 1:
            raise ValueError("parametric surface audit requires a positive source triangle count")
        if not self.allowed_surface_types:
            raise ValueError("parametric surface audit requires at least one allowed surface type")
        if len(self.allowed_surface_types) != len(set(self.allowed_surface_types)):
            raise ValueError("parametric surface audit types must be unique")
        unknown = sorted(set(self.allowed_surface_types) - set(PARAMETRIC_SURFACE_TYPES))
        if unknown:
            raise ValueError(f"unknown parametric surface types: {', '.join(unknown)}")
        if "other" in self.allowed_surface_types:
            raise ValueError("unclassified 'other' surfaces cannot be allowed as parametric")


@dataclass(frozen=True, slots=True)
class ParametricSurfaceIssue:
    code: str
    message: str
    measured: dict[str, int | str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "measured": dict(sorted(self.measured.items())),
        }


@dataclass(frozen=True, slots=True)
class ParametricSurfaceAudit:
    surface_counts: dict[str, int]
    allowed_surface_types: tuple[str, ...]
    source_triangle_count: int
    face_count: int
    issues: tuple[ParametricSurfaceIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "surfaceCounts": dict(sorted(self.surface_counts.items())),
            "allowedSurfaceTypes": list(self.allowed_surface_types),
            "sourceTriangleCount": self.source_triangle_count,
            "faceCount": self.face_count,
            "issues": [issue.to_dict() for issue in self.issues],
            "valid": self.valid,
        }


@dataclass(frozen=True, slots=True)
class ShapeValidation:
    root_type: str
    solid_count: int
    cadquery_valid: bool
    occt_valid: bool
    closed: bool
    positive_volume: bool
    volume: float
    area: float
    face_count: int
    edge_count: int
    vertex_count: int
    triangle_count: int
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "rootType": self.root_type,
            "solidCount": self.solid_count,
            "cadqueryValid": self.cadquery_valid,
            "occtValid": self.occt_valid,
            "closed": self.closed,
            "positiveVolume": self.positive_volume,
            "volume": self.volume,
            "area": self.area,
            "faceCount": self.face_count,
            "edgeCount": self.edge_count,
            "vertexCount": self.vertex_count,
            "triangleCount": self.triangle_count,
            "errors": list(self.errors),
            "valid": self.valid,
        }


@dataclass(frozen=True, slots=True)
class StepValidation:
    path: str
    source: ShapeValidation
    reimport: ShapeValidation
    volume_delta: float
    volume_tolerance: float
    topology_counts_match: bool
    sha256: str
    normalized: bool
    parametric_surface_audit: ParametricSurfaceAudit | None = None

    @property
    def valid(self) -> bool:
        return (
            self.source.valid
            and self.reimport.valid
            and self.volume_delta <= self.volume_tolerance
            and self.topology_counts_match
            and (
                self.parametric_surface_audit is None
                or self.parametric_surface_audit.valid
            )
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "path": self.path,
            "source": self.source.to_dict(),
            "reimport": self.reimport.to_dict(),
            "volumeDelta": self.volume_delta,
            "volumeTolerance": self.volume_tolerance,
            "topologyCountsMatch": self.topology_counts_match,
            "sha256": self.sha256,
            "normalized": self.normalized,
            "valid": self.valid,
        }
        if self.parametric_surface_audit is not None:
            result["parametricSurfaceAudit"] = self.parametric_surface_audit.to_dict()
        return result


def as_shape(value: cq.Shape | cq.Workplane) -> cq.Shape:
    if isinstance(value, cq.Workplane):
        candidate = value.val()
        if isinstance(candidate, cq.Shape):
            return candidate
        raise TypeError(f"workplane contains {type(candidate).__name__}, not a Shape")
    if isinstance(value, cq.Shape):
        return value
    raise TypeError(f"expected CadQuery Shape or Workplane, got {type(value).__name__}")


def validate_shape(
    value: cq.Shape | cq.Workplane,
    linear_resolution: float = 1e-3,
    angular_tolerance: float = 0.1,
    *,
    require_tessellation: bool = True,
) -> ShapeValidation:
    """Apply every kernel gate required before a feature can be accepted."""

    shape = as_shape(value)
    errors: list[str] = []
    solids = shape.Solids()
    if len(solids) != 1:
        errors.append(f"expected exactly one solid, got {len(solids)}")
    solid = solids[0] if len(solids) == 1 else None

    try:
        cadquery_valid = bool(shape.isValid())
    except (RuntimeError, ValueError):
        cadquery_valid = False
    if not cadquery_valid:
        errors.append("CadQuery validity check failed")

    try:
        occt_valid = bool(BRepCheck_Analyzer(shape.wrapped).IsValid())
    except (RuntimeError, ValueError):
        occt_valid = False
    if not occt_valid:
        errors.append("Open CASCADE BRepCheck_Analyzer failed")

    try:
        shells = solid.Shells() if solid is not None else []
        # TopoDS_Solid itself does not carry the Closed flag consistently;
        # closure is a property of each bounding shell.
        closed = bool(shells and all(shell.Closed() for shell in shells))
    except (RuntimeError, ValueError):
        closed = False
    if not closed:
        errors.append("result solid is not closed")

    try:
        volume = float(solid.Volume() if solid is not None else shape.Volume())
    except (RuntimeError, ValueError):
        volume = 0.0
    minimum_volume = max(float(linear_resolution) ** 3, 1e-15)
    positive_volume = volume > minimum_volume
    if not positive_volume:
        errors.append(f"result volume {volume:g} does not exceed minimum {minimum_volume:g}")

    vertex_count = 0
    triangle_count = 0
    if require_tessellation:
        try:
            vertices, triangles = shape.tessellate(
                max(float(linear_resolution), 1e-6),
                max(float(angular_tolerance), 1e-6),
            )
            vertex_count = len(vertices)
            triangle_count = len(triangles)
        except (RuntimeError, ValueError) as exc:
            errors.append(f"tessellation failed: {exc}")
        if vertex_count == 0 or triangle_count == 0:
            errors.append("tessellation is empty")

    return ShapeValidation(
        root_type=shape.ShapeType(),
        solid_count=len(solids),
        cadquery_valid=cadquery_valid,
        occt_valid=occt_valid,
        closed=closed,
        positive_volume=positive_volume,
        volume=volume,
        area=float(shape.Area()),
        face_count=len(shape.Faces()),
        edge_count=len(shape.Edges()),
        vertex_count=vertex_count,
        triangle_count=triangle_count,
        errors=tuple(dict.fromkeys(errors)),
    )


_STEP_FILE_NAME = re.compile(
    r"FILE_NAME\('[^']*','[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+(?:\.[0-9]+)?'"
)
_STEP_TRANSLATOR_SEQUENCE = re.compile(r"(Open CASCADE STEP translator [0-9.]+) [0-9]+")


def normalize_step_bytes(payload: bytes, *, model_name: str = "model") -> bytes:
    """Remove OCCT process/time counters without changing STEP geometry."""

    stable_name = re.sub(r"[^A-Za-z0-9._-]+", "_", model_name).strip("._-") or "model"
    text = payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    text, file_name_replacements = _STEP_FILE_NAME.subn(
        f"FILE_NAME('{stable_name}','1970-01-01T00:00:00'", text
    )
    if file_name_replacements != 1:
        raise ValueError(
            "unexpected Open CASCADE STEP header: expected exactly one FILE_NAME label, "
            f"replaced {file_name_replacements}"
        )
    text, translator_replacements = _STEP_TRANSLATOR_SEQUENCE.subn(r"\g<1> 1", text)
    if translator_replacements != 2:
        raise ValueError(
            "unexpected Open CASCADE STEP labels: expected exactly two translator counters, "
            f"replaced {translator_replacements}"
        )
    text = "\n".join(line.rstrip() for line in text.split("\n")).rstrip("\n") + "\n"
    return text.encode("utf-8")


def import_step_shape(path: str | Path, units: str = "mm") -> cq.Shape:
    step_unit = STEP_UNITS.get(units)
    if step_unit is None:
        raise ValueError(f"unsupported STEP unit {units!r}")
    source = Path(path)
    if source.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("STEP input must use a .step or .stp extension")
    if not source.is_file():
        raise ValueError(f"STEP input does not exist: {source}")
    try:
        candidate = cq.importers.importStep(
            str(source),
            unit=step_unit,  # type: ignore[arg-type]
        ).val()
        if not isinstance(candidate, cq.Shape):
            raise ValueError(f"STEP importer returned {type(candidate).__name__}, not a shape")
        return candidate
    except Exception as exc:  # OCCT raises several wrapped exception types.
        raise ValueError(f"failed to import STEP: {exc}") from exc


def export_step_validated(
    value: cq.Shape | cq.Workplane,
    path: str | Path,
    *,
    units: str = "mm",
    linear_resolution: float = 1e-3,
    angular_tolerance: float = 0.1,
    require_tessellation: bool = True,
    parametric_surface_policy: ParametricSurfacePolicy | None = None,
) -> StepValidation:
    """Export normalized STEP and prove it by kernel reimport before success."""

    shape = as_shape(value)
    source_validation = validate_shape(
        shape,
        linear_resolution,
        angular_tolerance,
        require_tessellation=require_tessellation,
    )
    if not source_validation.valid:
        raise ValueError(
            "refusing STEP export for invalid source B-Rep: " + "; ".join(source_validation.errors)
        )
    step_unit = STEP_UNITS.get(units)
    if step_unit is None:
        raise ValueError(f"unsupported STEP unit {units!r}")

    destination = Path(path)
    if destination.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("STEP output must use a .step or .stp extension")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp.step", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        cq.exporters.export(
            shape,
            str(temporary),
            exportType="STEP",
            unit=step_unit,  # type: ignore[arg-type]
        )
        normalized = normalize_step_bytes(temporary.read_bytes(), model_name=destination.stem)
        temporary.write_bytes(normalized)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

    imported = import_step_shape(destination, units)
    reimport_validation = validate_shape(
        imported,
        linear_resolution,
        angular_tolerance,
        require_tessellation=require_tessellation,
    )
    volume_delta = abs(source_validation.volume - reimport_validation.volume)
    source_surface_counts = classify_parametric_face_surfaces(shape)
    reimport_surface_counts = classify_parametric_face_surfaces(imported)
    contains_freeform_surface = any(
        source_surface_counts[surface_type] or reimport_surface_counts[surface_type]
        for surface_type in FREEFORM_STEP_SURFACE_TYPES
    )
    relative_volume_tolerance = 5e-6 if contains_freeform_surface else 1e-6
    volume_tolerance = max(
        linear_resolution**3 * 10,
        # OCCT STEP translation approximates intersection p-curves: a few
        # parts in 10^7 for mutually intersecting analytic surfaces, and up to
        # a few parts in 10^6 where a trimming curve crosses a freeform
        # B-spline face. Keep analytic sample metadata byte-stable at one part
        # per million and widen only when either exact shape contains a
        # freeform surface.
        abs(source_validation.volume) * relative_volume_tolerance,
        1e-12,
    )
    topology_counts_match = (
        source_validation.face_count == reimport_validation.face_count
        and source_validation.edge_count == reimport_validation.edge_count
    )
    parametric_surface_audit = (
        audit_parametric_surfaces(imported, parametric_surface_policy)
        if parametric_surface_policy is not None
        else None
    )
    report = StepValidation(
        path=str(destination),
        source=source_validation,
        reimport=reimport_validation,
        volume_delta=volume_delta,
        volume_tolerance=volume_tolerance,
        topology_counts_match=topology_counts_match,
        sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        normalized=True,
        parametric_surface_audit=parametric_surface_audit,
    )
    if not report.valid:
        surface_issues = (
            [issue.to_dict() for issue in parametric_surface_audit.issues]
            if parametric_surface_audit is not None
            else None
        )
        destination.unlink(missing_ok=True)
        failure = (
            "STEP round-trip validation failed: "
            f"reimport={reimport_validation.errors}, volumeDelta={volume_delta:g}, "
            f"topologyCountsMatch={topology_counts_match}"
        )
        if surface_issues is not None:
            failure += f", surfaceAudit={surface_issues}"
        raise ValueError(failure)
    return report


def validate_step_file(
    path: str | Path,
    *,
    units: str = "mm",
    linear_resolution: float = 1e-3,
    angular_tolerance: float = 0.1,
) -> ShapeValidation:
    return validate_shape(
        import_step_shape(path, units),
        linear_resolution,
        angular_tolerance,
    )


def classify_parametric_face_surfaces(value: cq.Shape | cq.Workplane) -> dict[str, int]:
    """Classify every OCCT surface without hiding unsupported kinds in a broad bucket."""

    result = dict.fromkeys(PARAMETRIC_SURFACE_TYPES, 0)
    mapping = {
        GeomAbs_Plane: "plane",
        GeomAbs_Cylinder: "cylinder",
        GeomAbs_Cone: "cone",
        GeomAbs_Sphere: "sphere",
        GeomAbs_Torus: "torus",
        GeomAbs_BSplineSurface: "bspline",
        GeomAbs_BezierSurface: "bezier",
        GeomAbs_SurfaceOfExtrusion: "surfaceOfExtrusion",
        GeomAbs_SurfaceOfRevolution: "surfaceOfRevolution",
        GeomAbs_OffsetSurface: "offset",
        GeomAbs_OtherSurface: "other",
    }
    for face in as_shape(value).Faces():
        surface_type = BRepAdaptor_Surface(face.wrapped, True).GetType()
        result[mapping.get(surface_type, "other")] += 1
    return result


def audit_parametric_surfaces(
    value: cq.Shape | cq.Workplane,
    policy: ParametricSurfacePolicy,
) -> ParametricSurfaceAudit:
    """Reject undeclared surfaces and triangle-per-face parametric claims."""

    policy.validate()
    counts = classify_parametric_face_surfaces(value)
    allowed = tuple(sorted(policy.allowed_surface_types))
    issues: list[ParametricSurfaceIssue] = []
    if counts["other"]:
        issues.append(
            ParametricSurfaceIssue(
                code="unclassified-surface-type",
                message="parametric candidate contains OCCT surfaces with no explicit class",
                measured={"surfaceType": "other", "faceCount": counts["other"]},
            )
        )
    for surface_type, count in sorted(counts.items()):
        if count and surface_type != "other" and surface_type not in allowed:
            issues.append(
                ParametricSurfaceIssue(
                    code="unsupported-surface-type",
                    message=(
                        f"parametric candidate contains undeclared {surface_type} surfaces"
                    ),
                    measured={"surfaceType": surface_type, "faceCount": count},
                )
            )
    face_count = sum(counts.values())
    if face_count >= policy.source_triangle_count:
        issues.append(
            ParametricSurfaceIssue(
                code="triangle-per-face-parametric-output",
                message=(
                    "parametric candidate has at least one B-Rep face per source triangle"
                ),
                measured={
                    "faceCount": face_count,
                    "sourceTriangleCount": policy.source_triangle_count,
                },
            )
        )
    return ParametricSurfaceAudit(
        surface_counts=counts,
        allowed_surface_types=allowed,
        source_triangle_count=policy.source_triangle_count,
        face_count=face_count,
        issues=tuple(issues),
    )


def classify_face_surfaces(value: cq.Shape | cq.Workplane) -> dict[str, int]:
    """Classify the exact OCCT surface underlying every B-Rep face."""

    result = {
        "plane": 0,
        "cylinder": 0,
        "cone": 0,
        "sphere": 0,
        "torus": 0,
        "bspline": 0,
        "other": 0,
    }
    mapping = {
        GeomAbs_Plane: "plane",
        GeomAbs_Cylinder: "cylinder",
        GeomAbs_Cone: "cone",
        GeomAbs_Sphere: "sphere",
        GeomAbs_Torus: "torus",
        GeomAbs_BSplineSurface: "bspline",
    }
    for face in as_shape(value).Faces():
        surface_type = BRepAdaptor_Surface(face.wrapped, True).GetType()
        result[mapping.get(surface_type, "other")] += 1
    return result


__all__ = [
    "FREEFORM_STEP_SURFACE_TYPES",
    "PARAMETRIC_SURFACE_TYPES",
    "STEP_UNITS",
    "ParametricSurfaceAudit",
    "ParametricSurfaceIssue",
    "ParametricSurfacePolicy",
    "ShapeValidation",
    "StepValidation",
    "as_shape",
    "audit_parametric_surfaces",
    "classify_face_surfaces",
    "classify_parametric_face_surfaces",
    "export_step_validated",
    "import_step_shape",
    "normalize_step_bytes",
    "validate_shape",
    "validate_step_file",
]
