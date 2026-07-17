"""Strict Pydantic v2 models for the CADGraph JSON Schema.

The JSON Schema in ``packages/contracts/schema`` is the compatibility source of
truth.  These models add graph-level invariants that are awkward to express in
portable JSON Schema (reference integrity, deterministic feature order and
orthonormal coordinate frames).
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


CURRENT_SCHEMA_VERSION = "1.0.0"


def _to_camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest)


Identifier = Annotated[
    str,
    Field(min_length=1, max_length=160, pattern=r"^[A-Za-z][A-Za-z0-9._:-]*$"),
]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
Timestamp = Annotated[
    str,
    Field(
        pattern=(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
            r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
        )
    ),
]
Units = Literal["mm", "cm", "m", "in", "ft"]
BooleanMode = Literal["base", "additive", "subtractive"]


class StrictModel(BaseModel):
    """Base class that rejects coercion and unknown properties."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        populate_by_name=True,
        strict=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
    )


class Vector2(StrictModel):
    x: float
    y: float


class Vector3(StrictModel):
    x: float
    y: float
    z: float


def _components(vector: Vector3) -> tuple[float, float, float]:
    return vector.x, vector.y, vector.z


def _norm(vector: Vector3) -> float:
    return math.sqrt(sum(value * value for value in _components(vector)))


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(_components(left), _components(right), strict=True))


def _require_unit(vector: Vector3, label: str, *, tolerance: float = 1e-6) -> None:
    magnitude = _norm(vector)
    if not math.isclose(magnitude, 1.0, rel_tol=0.0, abs_tol=tolerance):
        raise ValueError(f"{label} must be a unit vector; magnitude is {magnitude:g}")


def _require_nonzero(vector: Vector3, label: str) -> None:
    if _norm(vector) <= 1e-12:
        raise ValueError(f"{label} must be non-zero")


class Axis3(StrictModel):
    origin: Vector3
    direction: Vector3

    @model_validator(mode="after")
    def validate_direction(self) -> Axis3:
        _require_nonzero(self.direction, "axis direction")
        return self


class Plane3(StrictModel):
    origin: Vector3
    normal: Vector3
    x_axis: Vector3

    @model_validator(mode="after")
    def validate_basis(self) -> Plane3:
        _require_unit(self.normal, "plane normal")
        _require_unit(self.x_axis, "plane xAxis")
        if not math.isclose(_dot(self.normal, self.x_axis), 0.0, abs_tol=1e-6):
            raise ValueError("plane normal and xAxis must be perpendicular")
        return self


class SourceAsset(StrictModel):
    format: Literal["stl", "obj", "ply", "cadgraph", "generated"]
    sha256: Sha256
    original_file_name: Annotated[str, Field(min_length=1, max_length=255)]
    byte_size: Annotated[int, Field(ge=0)]
    triangle_count: Annotated[int, Field(ge=0)] | None = None
    declared_units: Units | None = None
    scale_factor: PositiveFloat | None = None


class SourceCoordinateFrame(StrictModel):
    origin: Vector3
    x_axis: Vector3
    y_axis: Vector3
    z_axis: Vector3
    locked: bool
    confidence: Confidence
    evidence_ids: list[Identifier]

    @model_validator(mode="after")
    def validate_orthonormal_frame(self) -> SourceCoordinateFrame:
        axes = (("xAxis", self.x_axis), ("yAxis", self.y_axis), ("zAxis", self.z_axis))
        for name, axis in axes:
            _require_unit(axis, name)
        for (left_name, left), (right_name, right) in (
            (axes[0], axes[1]),
            (axes[0], axes[2]),
            (axes[1], axes[2]),
        ):
            if not math.isclose(_dot(left, right), 0.0, abs_tol=1e-6):
                raise ValueError(f"{left_name} and {right_name} must be perpendicular")
        return self


class ProjectTolerance(StrictModel):
    surface_deviation: PositiveFloat
    angular_deviation_deg: Annotated[float, Field(gt=0.0, le=180.0)]
    linear_resolution: PositiveFloat


class SourceEvidence(StrictModel):
    id: Identifier
    source_type: Literal[
        "meshPatch",
        "meshTriangle",
        "sketchEntity",
        "feature",
        "user",
        "engine",
        "imported",
        "derived",
    ]
    source_ids: list[Identifier]
    measured_value: float | None = None
    suggested_nominal_value: float | None = None
    residual: NonNegativeFloat | None = None
    confidence: Confidence
    notes: Annotated[str, Field(max_length=2000)] | None = None
    metadata: dict[str, JsonValue] | None = None


class UserLock(StrictModel):
    target: Identifier
    locked: bool
    reason: Annotated[str, Field(max_length=1000)]
    locked_at: Timestamp | None = None
    locked_by: Annotated[str, Field(max_length=200)] | None = None


class UserOverride(StrictModel):
    target: Identifier
    value: JsonValue
    previous_value: JsonValue | None = None
    reason: Annotated[str, Field(max_length=1000)]
    created_at: Timestamp | None = None
    created_by: Annotated[str, Field(max_length=200)] | None = None


class EntityBase(StrictModel):
    id: Identifier
    name: Annotated[str, Field(max_length=200)] | None = None
    construction: bool
    source_evidence: list[Identifier]
    confidence: Confidence
    locked: bool
    suppressed: bool


class PointEntity(EntityBase):
    kind: Literal["point"]
    construction: Literal[False]
    position: Vector2


class ConstructionPointEntity(EntityBase):
    kind: Literal["constructionPoint"]
    construction: Literal[True]
    position: Vector2


class LineEntity(EntityBase):
    kind: Literal["line"]
    construction: Literal[False]
    start: Vector2
    end: Vector2

    @model_validator(mode="after")
    def validate_length(self) -> LineEntity:
        if self.start == self.end:
            raise ValueError("line start and end must differ")
        return self


class ConstructionLineEntity(EntityBase):
    kind: Literal["constructionLine"]
    construction: Literal[True]
    start: Vector2
    end: Vector2

    @model_validator(mode="after")
    def validate_length(self) -> ConstructionLineEntity:
        if self.start == self.end:
            raise ValueError("construction line start and end must differ")
        return self


class PolylineEntity(EntityBase):
    kind: Literal["polyline"]
    construction: Literal[False]
    points: Annotated[list[Vector2], Field(min_length=2)]
    closed: bool


class RectangleEntity(EntityBase):
    kind: Literal["rectangle"]
    construction: Literal[False]
    origin: Vector2
    width: PositiveFloat
    height: PositiveFloat
    rotation_deg: float


class CircleEntity(EntityBase):
    kind: Literal["circle"]
    construction: Literal[False]
    center: Vector2
    radius: PositiveFloat


class CircularArcEntity(EntityBase):
    kind: Literal["circularArc"]
    construction: Literal[False]
    center: Vector2
    radius: PositiveFloat
    start_angle_deg: float
    end_angle_deg: float
    clockwise: bool

    @model_validator(mode="after")
    def validate_sweep(self) -> CircularArcEntity:
        if math.isclose(self.start_angle_deg, self.end_angle_deg, abs_tol=1e-12):
            raise ValueError("circular arc must have a non-zero sweep")
        return self


class ClosedProfileEntity(EntityBase):
    kind: Literal["closedProfile"]
    construction: Literal[False]
    outer_loop: Annotated[list[Identifier], Field(min_length=1)]
    inner_loops: list[Annotated[list[Identifier], Field(min_length=1)]]
    orientation: Literal["clockwise", "counterclockwise"]


class ConstructionAxisEntity(EntityBase):
    kind: Literal["constructionAxis"]
    construction: Literal[True]
    origin: Vector2
    direction: Vector2

    @model_validator(mode="after")
    def validate_direction(self) -> ConstructionAxisEntity:
        if math.hypot(self.direction.x, self.direction.y) <= 1e-12:
            raise ValueError("construction axis direction must be non-zero")
        return self


SketchEntity = Annotated[
    PointEntity
    | ConstructionPointEntity
    | LineEntity
    | ConstructionLineEntity
    | PolylineEntity
    | RectangleEntity
    | CircleEntity
    | CircularArcEntity
    | ClosedProfileEntity
    | ConstructionAxisEntity,
    Field(discriminator="kind"),
]


class SketchConstraint(StrictModel):
    id: Identifier
    kind: Literal[
        "horizontal",
        "vertical",
        "coincident",
        "parallel",
        "perpendicular",
        "equalLength",
        "equalRadius",
        "concentric",
        "tangent",
        "symmetric",
        "fixed",
        "distance",
        "horizontalDistance",
        "verticalDistance",
        "angle",
        "radius",
        "diameter",
    ]
    entity_ids: Annotated[list[Identifier], Field(min_length=1)]
    value: float | None = None
    measured_value: float | None = None
    suggested_nominal_value: float | None = None
    nominal_accepted: bool | None = None
    unit: Literal["length", "angle", "none"] | None = None
    driving: bool
    source_evidence: list[Identifier]
    confidence: Confidence
    locked: bool

    @model_validator(mode="after")
    def validate_dimension(self) -> SketchConstraint:
        dimensional = {"distance", "horizontalDistance", "verticalDistance", "angle", "radius", "diameter"}
        if self.kind in dimensional and self.value is None:
            raise ValueError(f"{self.kind} constraint requires value")
        if self.kind in {"radius", "diameter"} and self.value is not None and self.value <= 0:
            raise ValueError(f"{self.kind} constraint value must be positive")
        return self


class SketchProfile(StrictModel):
    id: Identifier
    name: Annotated[str, Field(max_length=200)] | None = None
    outer_loop: Annotated[list[Identifier], Field(min_length=1)]
    inner_loops: list[Annotated[list[Identifier], Field(min_length=1)]]
    orientation: Literal["clockwise", "counterclockwise"]
    closed: Literal[True]
    source_evidence: list[Identifier]
    confidence: Confidence
    locked: bool


class Sketch(StrictModel):
    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=200)]
    plane: Plane3
    entities: list[SketchEntity]
    constraints: list[SketchConstraint]
    profiles: list[SketchProfile]
    source_evidence: list[Identifier]
    confidence: Confidence
    user_locks: list[UserLock]
    overrides: list[UserOverride]
    suppressed: bool

    @model_validator(mode="after")
    def validate_local_references(self) -> Sketch:
        entity_ids = _unique_ids(self.entities, f"sketch {self.id} entities")
        _unique_ids(self.constraints, f"sketch {self.id} constraints")
        _unique_ids(self.profiles, f"sketch {self.id} profiles")
        for constraint in self.constraints:
            _require_subset(constraint.entity_ids, entity_ids, f"constraint {constraint.id} entityIds")
        for profile in self.profiles:
            _require_subset(profile.outer_loop, entity_ids, f"profile {profile.id} outerLoop")
            for index, loop in enumerate(profile.inner_loops):
                _require_subset(loop, entity_ids, f"profile {profile.id} innerLoops[{index}]")
        for entity in self.entities:
            if isinstance(entity, ClosedProfileEntity):
                targets = [*entity.outer_loop, *(item for loop in entity.inner_loops for item in loop)]
                _require_subset(targets, entity_ids - {entity.id}, f"closed profile entity {entity.id}")
        return self


class FeatureBase(StrictModel):
    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=200)]
    order: Annotated[int, Field(ge=0)]
    dependencies: list[Identifier]
    suppressed: bool
    source_evidence: list[Identifier]
    confidence: Confidence
    user_locks: list[UserLock]
    overrides: list[UserOverride]
    semantic_outputs: list[Identifier]


class ExtrusionFeature(FeatureBase):
    operation: Literal["extrusion"]
    boolean_mode: BooleanMode
    sketch_id: Identifier
    profile_ids: Annotated[list[Identifier], Field(min_length=1)]
    direction: Vector3
    extent: Literal["blind", "symmetric", "throughAll", "toFace"]
    distance: PositiveFloat | None = None
    target_face: Identifier | None = None

    @model_validator(mode="after")
    def validate_extent(self) -> ExtrusionFeature:
        _require_nonzero(self.direction, "extrusion direction")
        if self.extent in {"blind", "symmetric"} and self.distance is None:
            raise ValueError(f"{self.extent} extrusion requires distance")
        if self.extent == "toFace" and self.target_face is None:
            raise ValueError("toFace extrusion requires targetFace")
        return self


class PocketFeature(FeatureBase):
    operation: Literal["pocket"]
    boolean_mode: Literal["subtractive"]
    sketch_id: Identifier
    profile_ids: Annotated[list[Identifier], Field(min_length=1)]
    direction: Vector3
    extent: Literal["blind", "throughAll", "toFace"]
    depth: PositiveFloat
    target_face: Identifier | None = None

    @model_validator(mode="after")
    def validate_extent(self) -> PocketFeature:
        _require_nonzero(self.direction, "pocket direction")
        if self.extent == "toFace" and self.target_face is None:
            raise ValueError("toFace pocket requires targetFace")
        return self


class HoleFeature(FeatureBase):
    operation: Literal["hole"]
    boolean_mode: Literal["subtractive"]
    hole_type: Literal["through", "blind"]
    position: Vector3
    axis: Vector3
    diameter: PositiveFloat
    depth: PositiveFloat | None = None
    termination_face: Identifier | None = None

    @model_validator(mode="after")
    def validate_hole(self) -> HoleFeature:
        _require_nonzero(self.axis, "hole axis")
        if self.hole_type == "blind" and self.depth is None:
            raise ValueError("blind hole requires depth")
        return self


class CounterboreFeature(FeatureBase):
    operation: Literal["counterbore"]
    boolean_mode: Literal["subtractive"]
    hole_type: Literal["through", "blind"]
    position: Vector3
    axis: Vector3
    diameter: PositiveFloat
    depth: PositiveFloat | None = None
    bore_diameter: PositiveFloat
    bore_depth: PositiveFloat

    @model_validator(mode="after")
    def validate_counterbore(self) -> CounterboreFeature:
        _require_nonzero(self.axis, "counterbore axis")
        if self.hole_type == "blind" and self.depth is None:
            raise ValueError("blind counterbore requires depth")
        if self.bore_diameter <= self.diameter:
            raise ValueError("boreDiameter must be greater than diameter")
        if self.depth is not None and self.bore_depth >= self.depth:
            raise ValueError("boreDepth must be less than hole depth")
        return self


class CountersinkFeature(FeatureBase):
    operation: Literal["countersink"]
    boolean_mode: Literal["subtractive"]
    hole_type: Literal["through", "blind"]
    position: Vector3
    axis: Vector3
    diameter: PositiveFloat
    depth: PositiveFloat | None = None
    sink_diameter: PositiveFloat
    sink_angle_deg: Annotated[float, Field(gt=0.0, lt=180.0)]

    @model_validator(mode="after")
    def validate_countersink(self) -> CountersinkFeature:
        _require_nonzero(self.axis, "countersink axis")
        if self.hole_type == "blind" and self.depth is None:
            raise ValueError("blind countersink requires depth")
        if self.sink_diameter <= self.diameter:
            raise ValueError("sinkDiameter must be greater than diameter")
        return self


class RevolutionFeature(FeatureBase):
    operation: Literal["revolution"]
    boolean_mode: BooleanMode
    sketch_id: Identifier
    profile_ids: Annotated[list[Identifier], Field(min_length=1)]
    axis: Axis3
    angle_deg: Annotated[float, Field(gt=0.0, le=360.0)]


class LinearPatternFeature(FeatureBase):
    operation: Literal["linearPattern"]
    source_feature_ids: Annotated[list[Identifier], Field(min_length=1)]
    direction: Vector3
    count: Annotated[int, Field(ge=2)]
    spacing: PositiveFloat

    @model_validator(mode="after")
    def validate_direction(self) -> LinearPatternFeature:
        _require_nonzero(self.direction, "linear pattern direction")
        return self


class CircularPatternFeature(FeatureBase):
    operation: Literal["circularPattern"]
    source_feature_ids: Annotated[list[Identifier], Field(min_length=1)]
    axis: Axis3
    count: Annotated[int, Field(ge=2)]
    total_angle_deg: Annotated[float, Field(gt=0.0, le=360.0)]


class MirrorFeature(FeatureBase):
    operation: Literal["mirror"]
    source_feature_ids: Annotated[list[Identifier], Field(min_length=1)]
    plane: Plane3
    keep_originals: bool


class ChamferFeature(FeatureBase):
    operation: Literal["chamfer"]
    target_edges: Annotated[list[Identifier], Field(min_length=1)]
    width: PositiveFloat


class FilletFeature(FeatureBase):
    operation: Literal["fillet"]
    target_edges: Annotated[list[Identifier], Field(min_length=1)]
    radius: PositiveFloat


class ImportedFacetedFeature(FeatureBase):
    operation: Literal["importedFaceted"]
    boolean_mode: BooleanMode
    source_artifact_id: Identifier
    mesh_sha256: Sha256
    intent: Literal["fallback", "reference"]
    sewing_tolerance: Annotated[float, Field(gt=0.0, le=10.0)] | None = None


class ReconstructedSurfaceNetworkFeature(FeatureBase):
    """Approximate curved B-Rep base body rebuilt from a plate artifact.

    The referenced content-addressed artifact (``mesh2param/curved-plate/1``)
    carries the fitted surface network and its plate closure; the compiler
    rebuilds the identical solid deterministically. The geometry is a
    tolerance-controlled approximation of the source mesh, never recovered
    design history.
    """

    operation: Literal["reconstructedSurfaceNetwork"]
    source_artifact_id: Identifier
    artifact_sha256: Sha256


Feature = Annotated[
    ExtrusionFeature
    | PocketFeature
    | HoleFeature
    | CounterboreFeature
    | CountersinkFeature
    | RevolutionFeature
    | LinearPatternFeature
    | CircularPatternFeature
    | MirrorFeature
    | ChamferFeature
    | FilletFeature
    | ImportedFacetedFeature
    | ReconstructedSurfaceNetworkFeature,
    Field(discriminator="operation"),
]


class SemanticTopologyReference(StrictModel):
    id: Identifier
    kind: Literal["solid", "shell", "face", "wire", "edge", "vertex", "axis", "plane"]
    producer_feature_id: Identifier
    role: Annotated[str, Field(min_length=1, max_length=200)]
    generated_from: list[Identifier]
    status: Literal["resolved", "unresolved"]
    kernel_reference: str | None = None
    last_resolved_at: Timestamp | None = None


class ScoreWeights(StrictModel):
    rms_distance: NonNegativeFloat
    p95_distance: NonNegativeFloat
    max_distance: NonNegativeFloat
    normal_agreement: NonNegativeFloat
    volume_difference: NonNegativeFloat
    overlap: NonNegativeFloat
    sharp_edge_alignment: NonNegativeFloat
    boundary_alignment: NonNegativeFloat
    unmatched_source: NonNegativeFloat
    excess_result: NonNegativeFloat
    complexity: NonNegativeFloat
    unsupported_operation: NonNegativeFloat
    evidence_confidence: NonNegativeFloat


class ReconstructionSettings(StrictModel):
    max_features: Annotated[int, Field(ge=1)]
    beam_width: Annotated[int, Field(ge=1)]
    candidates_per_residual: Annotated[int, Field(ge=1)]
    wall_clock_seconds: PositiveFloat
    max_rebuilds: Annotated[int, Field(ge=1)]
    min_score_improvement: NonNegativeFloat
    nominal_snapping_enabled: bool
    nominal_snap_tolerance: NonNegativeFloat
    score_weights: ScoreWeights


class EngineVersions(StrictModel):
    mesh2param: Annotated[str, Field(min_length=1)]
    contracts: Annotated[str, Field(min_length=1)]
    cad_backend: Literal["OCCT"]
    cad_query: Annotated[str, Field(min_length=1)]
    ocp: Annotated[str, Field(min_length=1)]
    dependencies: dict[str, str]


class FitMetrics(StrictModel):
    rms_surface_distance: NonNegativeFloat
    p95_surface_distance: NonNegativeFloat
    max_surface_distance: NonNegativeFloat
    normal_agreement: Confidence
    volume_difference: NonNegativeFloat
    overlap: Confidence
    unmatched_source_area: NonNegativeFloat
    excess_result_area: NonNegativeFloat
    score: float


class ValidationIssue(StrictModel):
    code: Annotated[str, Field(min_length=1)]
    message: Annotated[str, Field(min_length=1)]
    severity: Literal["info", "warning", "error"]
    feature_id: Identifier | None = None
    semantic_reference: Identifier | None = None
    details: dict[str, JsonValue] | None = None


class ValidationStatus(StrictModel):
    status: Literal["notRun", "pending", "valid", "invalid", "partial"]
    brep_valid: bool | None
    step_reimport_valid: bool | None
    tolerance_satisfied: bool | None
    checked_at: Timestamp | None = None
    last_valid_feature_id: Identifier | None = None
    issues: list[ValidationIssue]

    @model_validator(mode="after")
    def validate_claim(self) -> ValidationStatus:
        if self.status == "valid" and not (
            self.brep_valid is True
            and self.step_reimport_valid is True
            and self.tolerance_satisfied is True
        ):
            raise ValueError(
                "valid status requires brepValid, stepReimportValid and toleranceSatisfied"
            )
        return self


class VersionMetadata(StrictModel):
    version_id: Identifier
    parent_version_id: Identifier | None = None
    created_at: Timestamp
    created_by: Annotated[str, Field(min_length=1, max_length=200)]
    message: Annotated[str, Field(max_length=1000)]


def _unique_ids(items: list[object], label: str) -> set[str]:
    values = [getattr(item, "id") for item in items]
    if len(values) != len(set(values)):
        duplicates = sorted({item for item in values if values.count(item) > 1})
        raise ValueError(f"{label} must be unique; duplicate IDs: {', '.join(duplicates)}")
    return set(values)


def _require_subset(values: list[str], allowed: set[str], label: str) -> None:
    missing = sorted(set(values) - allowed)
    if missing:
        raise ValueError(f"{label} contains unknown references: {', '.join(missing)}")


class CADGraph(StrictModel):
    schema_version: Literal["1.0.0"]
    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=200)]
    units: Units
    source: SourceAsset | None = None
    source_coordinate_frame: SourceCoordinateFrame
    project_tolerance: ProjectTolerance
    sketches: list[Sketch]
    features: list[Feature]
    semantic_topology: list[SemanticTopologyReference]
    source_evidence: list[SourceEvidence]
    user_locks: list[UserLock]
    overrides: list[UserOverride]
    reconstruction_settings: ReconstructionSettings
    engine_versions: EngineVersions
    deterministic_seed: Annotated[int, Field(ge=0, le=4_294_967_295)]
    fit_metrics: FitMetrics
    validation: ValidationStatus
    version_metadata: VersionMetadata
    extensions: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_graph(self) -> CADGraph:
        sketch_ids = _unique_ids(self.sketches, "sketch IDs")
        feature_ids = _unique_ids(self.features, "feature IDs")
        topology_ids = _unique_ids(self.semantic_topology, "semantic topology IDs")
        evidence_ids = _unique_ids(self.source_evidence, "source evidence IDs")

        orders = [feature.order for feature in self.features]
        if orders != sorted(orders):
            raise ValueError("features must be serialized in ascending order")
        if len(orders) != len(set(orders)):
            raise ValueError("feature order values must be unique")

        feature_order = {feature.id: feature.order for feature in self.features}
        profile_ids = {profile.id for sketch in self.sketches for profile in sketch.profiles}
        for feature in self.features:
            _require_subset(feature.dependencies, feature_ids, f"feature {feature.id} dependencies")
            for dependency in feature.dependencies:
                if feature_order[dependency] >= feature.order:
                    raise ValueError(
                        f"feature {feature.id} dependency {dependency} must have an earlier order"
                    )
            _require_subset(feature.source_evidence, evidence_ids, f"feature {feature.id} sourceEvidence")
            _require_subset(feature.semantic_outputs, topology_ids, f"feature {feature.id} semanticOutputs")
            if isinstance(feature, (ExtrusionFeature, PocketFeature, RevolutionFeature)):
                _require_subset([feature.sketch_id], sketch_ids, f"feature {feature.id} sketchId")
                _require_subset(feature.profile_ids, profile_ids, f"feature {feature.id} profileIds")
            if isinstance(feature, (LinearPatternFeature, CircularPatternFeature, MirrorFeature)):
                _require_subset(
                    feature.source_feature_ids,
                    set(feature.dependencies),
                    f"feature {feature.id} sourceFeatureIds (must also be dependencies)",
                )

        for sketch in self.sketches:
            _require_subset(sketch.source_evidence, evidence_ids, f"sketch {sketch.id} sourceEvidence")
            for entity in sketch.entities:
                _require_subset(
                    entity.source_evidence,
                    evidence_ids,
                    f"entity {entity.id} sourceEvidence",
                )
            for constraint in sketch.constraints:
                _require_subset(
                    constraint.source_evidence,
                    evidence_ids,
                    f"constraint {constraint.id} sourceEvidence",
                )
            for profile in sketch.profiles:
                _require_subset(
                    profile.source_evidence,
                    evidence_ids,
                    f"profile {profile.id} sourceEvidence",
                )

        for reference in self.semantic_topology:
            _require_subset(
                [reference.producer_feature_id],
                feature_ids,
                f"semantic topology {reference.id} producerFeatureId",
            )
        if self.validation.last_valid_feature_id is not None:
            _require_subset(
                [self.validation.last_valid_feature_id],
                feature_ids,
                "validation lastValidFeatureId",
            )
        return self


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "CADGraph",
    "Feature",
    "SketchEntity",
    "ExtrusionFeature",
    "PocketFeature",
    "HoleFeature",
    "CounterboreFeature",
    "CountersinkFeature",
    "RevolutionFeature",
    "LinearPatternFeature",
    "CircularPatternFeature",
    "MirrorFeature",
    "ChamferFeature",
    "FilletFeature",
    "ImportedFacetedFeature",
    "ReconstructedSurfaceNetworkFeature",
]
