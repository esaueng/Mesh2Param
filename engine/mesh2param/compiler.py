"""Deterministic feature-by-feature compiler for authoritative CADGraph documents."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from copy import copy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

import cadquery as cq
import trimesh
from mesh2param_contracts import CADGraph
from mesh2param_contracts.models import (
    ChamferFeature,
    CircleEntity,
    CircularArcEntity,
    CircularPatternFeature,
    ClosedProfileEntity,
    CounterboreFeature,
    CountersinkFeature,
    ExtrusionFeature,
    FilletFeature,
    HoleFeature,
    ImportedFacetedFeature,
    LinearPatternFeature,
    LineEntity,
    MirrorFeature,
    PocketFeature,
    PolylineEntity,
    RectangleEntity,
    RevolutionFeature,
    Sketch,
    SketchProfile,
)

from .errors import CompilationException, CompileError, FeatureBuildFailure
from .topology import ProvenanceRecord, ResolvedTopology, TopologyRegistry, topology_hash
from .validation import ShapeValidation, import_step_shape, validate_shape

type ArtifactResolver = Mapping[str, str | Path] | Callable[[str], str | Path]


@dataclass(frozen=True, slots=True)
class FeatureRecord:
    feature_id: str
    feature_type: str
    order: int
    status: str
    volume_before: float | None
    volume_after: float | None
    validation: ShapeValidation | None
    semantic_outputs: tuple[str, ...]
    topology_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["validation"] = self.validation.to_dict() if self.validation else None
        return result


@dataclass(slots=True)
class CompilationResult:
    success: bool
    shape: cq.Shape | None
    last_valid_feature_id: str | None
    feature_records: list[FeatureRecord] = field(default_factory=list)
    errors: list[CompileError] = field(default_factory=list)
    topology: dict[str, ResolvedTopology] = field(default_factory=dict)
    topology_issues: list[Any] = field(default_factory=list)
    provenance: list[ProvenanceRecord] = field(default_factory=list)

    def require_shape(self) -> cq.Shape:
        if not self.success or self.shape is None:
            raise CompilationException(
                "CADGraph did not compile completely; inspect feature-scoped errors",
                self.errors,
            )
        return self.shape

    def require_last_valid_shape(self) -> cq.Shape:
        if self.shape is None:
            raise CompilationException("CADGraph has no valid feature result", self.errors)
        return self.shape

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "lastValidFeatureId": self.last_valid_feature_id,
            "featureRecords": [record.to_dict() for record in self.feature_records],
            "errors": [error.to_dict() for error in self.errors],
            "topology": {key: value.to_dict() for key, value in sorted(self.topology.items())},
            "topologyIssues": [issue.to_dict() for issue in self.topology_issues],
            "provenance": [record.to_dict() for record in self.provenance],
        }


@dataclass(slots=True)
class _FeatureState:
    mode: str
    tool: cq.Shape
    body_before: cq.Shape | None
    body_after: cq.Shape


def _vector(value: Any) -> cq.Vector:
    return cq.Vector(float(value.x), float(value.y), float(value.z))


def _unit(value: Any, label: str) -> cq.Vector:
    vector = _vector(value)
    magnitude = vector.Length
    if magnitude <= 1e-12:
        raise FeatureBuildFailure(
            "invalid_direction",
            f"{label} vector has zero length",
            f"Provide a non-zero {label} vector.",
        )
    return vector.multiply(1.0 / magnitude)


def _plane(sketch: Sketch) -> cq.Plane:
    return cq.Plane(
        origin=_vector(sketch.plane.origin),
        xDir=_vector(sketch.plane.x_axis),
        normal=_vector(sketch.plane.normal),
    )


def _rotated_rectangle_points(entity: RectangleEntity) -> list[tuple[float, float]]:
    origin = (float(entity.origin.x), float(entity.origin.y))
    points = (
        (0.0, 0.0),
        (float(entity.width), 0.0),
        (float(entity.width), float(entity.height)),
        (0.0, float(entity.height)),
    )
    angle = math.radians(float(entity.rotation_deg))
    cosine, sine = math.cos(angle), math.sin(angle)
    return [
        (
            origin[0] + x * cosine - y * sine,
            origin[1] + x * sine + y * cosine,
        )
        for x, y in points
    ]


def _wire_for_entity(entity: Any, plane: cq.Plane) -> cq.Wire:
    workplane = cq.Workplane(plane)
    if isinstance(entity, RectangleEntity):
        points = _rotated_rectangle_points(entity)
        return cast(cq.Wire, workplane.polyline(points).close().val())
    if isinstance(entity, CircleEntity):
        return cast(
            cq.Wire,
            workplane.moveTo(float(entity.center.x), float(entity.center.y))
            .circle(float(entity.radius))
            .val(),
        )
    if isinstance(entity, PolylineEntity):
        if not entity.closed:
            raise FeatureBuildFailure(
                "open_profile",
                f"polyline {entity.id} is not closed",
                "Close the profile before using it in a solid feature.",
            )
        points = [(float(point.x), float(point.y)) for point in entity.points]
        return cast(cq.Wire, workplane.polyline(points).close().val())
    raise FeatureBuildFailure(
        "unsupported_profile_entity",
        f"entity {entity.id} ({entity.kind}) cannot independently define a profile wire",
        "Use a rectangle, circle, closed polyline, closedProfile, or connected line/arc loop.",
    )


def _arc_points(entity: CircularArcEntity) -> tuple[tuple[float, float], ...]:
    start = math.radians(float(entity.start_angle_deg))
    end = math.radians(float(entity.end_angle_deg))
    sweep = -((start - end) % (2 * math.pi)) if entity.clockwise else (end - start) % (2 * math.pi)
    if math.isclose(sweep, 0.0, abs_tol=1e-12):
        raise FeatureBuildFailure(
            "zero_arc_sweep",
            f"arc {entity.id} has zero sweep",
            "Provide distinct start and end angles.",
        )

    def point(angle: float) -> tuple[float, float]:
        return (
            float(entity.center.x) + float(entity.radius) * math.cos(angle),
            float(entity.center.y) + float(entity.radius) * math.sin(angle),
        )

    return point(start), point(start + sweep / 2), point(start + sweep)


def _wire_from_loop(sketch: Sketch, identifiers: Sequence[str]) -> cq.Wire:
    entities = {entity.id: entity for entity in sketch.entities if not entity.suppressed}
    if len(identifiers) == 1:
        entity = entities.get(identifiers[0])
        if entity is None:
            raise FeatureBuildFailure(
                "missing_profile_entity",
                f"profile references unavailable entity {identifiers[0]!r}",
                "Restore the referenced sketch entity or edit the profile.",
            )
        if isinstance(entity, ClosedProfileEntity):
            return _wire_from_loop(sketch, entity.outer_loop)
        return _wire_for_entity(entity, _plane(sketch))

    workplane = cq.Workplane(_plane(sketch))
    started = False
    current: tuple[float, float] | None = None
    for identifier in identifiers:
        entity = entities.get(identifier)
        if entity is None:
            raise FeatureBuildFailure(
                "missing_profile_entity",
                f"profile references unavailable entity {identifier!r}",
                "Restore the referenced sketch entity or edit the profile.",
            )
        if isinstance(entity, LineEntity):
            start = (float(entity.start.x), float(entity.start.y))
            end = (float(entity.end.x), float(entity.end.y))
            if not started:
                workplane = workplane.moveTo(*start)
                current = start
                started = True
            if current is None or not (
                math.isclose(current[0], start[0], abs_tol=1e-8)
                and math.isclose(current[1], start[1], abs_tol=1e-8)
            ):
                raise FeatureBuildFailure(
                    "disconnected_profile",
                    f"line {identifier} does not continue the preceding profile entity",
                    "Join profile entities end-to-start in authored order.",
                )
            workplane = workplane.lineTo(*end)
            current = end
        elif isinstance(entity, CircularArcEntity):
            start, middle, end = _arc_points(entity)
            if not started:
                workplane = workplane.moveTo(*start)
                current = start
                started = True
            if current is None or not (
                math.isclose(current[0], start[0], abs_tol=1e-8)
                and math.isclose(current[1], start[1], abs_tol=1e-8)
            ):
                raise FeatureBuildFailure(
                    "disconnected_profile",
                    f"arc {identifier} does not continue the preceding profile entity",
                    "Join profile entities end-to-start in authored order.",
                )
            workplane = workplane.threePointArc(middle, end)
            current = end
        else:
            raise FeatureBuildFailure(
                "unsupported_profile_entity",
                f"entity {identifier} ({entity.kind}) is unsupported in a composite loop",
                "Use connected line and circularArc entities for composite loops.",
            )
    if not started:
        raise FeatureBuildFailure(
            "empty_profile",
            "profile has no buildable entities",
            "Add at least one closed profile entity.",
        )
    return cast(cq.Wire, workplane.close().val())


def _face_for_profile(sketch: Sketch, profile: SketchProfile) -> cq.Face:
    outer = _wire_from_loop(sketch, profile.outer_loop)
    inners = [_wire_from_loop(sketch, loop) for loop in profile.inner_loops]
    try:
        face = cq.Face.makeFromWires(outer, inners)
    except Exception as exc:
        raise FeatureBuildFailure(
            "invalid_profile",
            f"profile {profile.id} could not form a face: {exc}",
            "Remove self-intersections and ensure inner loops are nested and non-touching.",
        ) from exc
    if not face.isValid() or face.Area() <= 1e-15:
        raise FeatureBuildFailure(
            "invalid_profile",
            f"profile {profile.id} produced an invalid or zero-area face",
            "Remove self-intersections and close every loop.",
        )
    return face


def _profiles(graph: CADGraph, sketch_id: str, profile_ids: Sequence[str]) -> list[cq.Face]:
    sketch = next((item for item in graph.sketches if item.id == sketch_id), None)
    if sketch is None or sketch.suppressed:
        raise FeatureBuildFailure(
            "missing_sketch",
            f"sketch {sketch_id!r} is unavailable",
            "Restore the referenced sketch or suppress the dependent feature.",
        )
    profiles = {profile.id: profile for profile in sketch.profiles}
    result: list[cq.Face] = []
    for profile_id in profile_ids:
        profile = profiles.get(profile_id)
        if profile is None:
            raise FeatureBuildFailure(
                "missing_profile",
                f"profile {profile_id!r} is unavailable in sketch {sketch_id!r}",
                "Select an existing closed profile.",
            )
        result.append(_face_for_profile(sketch, profile))
    return result


def _shape_from_solids(solids: Sequence[cq.Shape]) -> cq.Shape:
    if len(solids) == 1:
        return solids[0]
    return cq.Compound.makeCompound(list(solids))


def _single_solid(shape: cq.Shape) -> cq.Solid:
    solids = shape.Solids()
    if len(solids) != 1:
        raise FeatureBuildFailure(
            "solid_count",
            f"feature result contains {len(solids)} solids; exactly one is required",
            "Make the feature intersect the primary body or suppress disconnected geometry.",
        )
    return solids[0]


def _bbox_corners(shape: cq.Shape) -> tuple[cq.Vector, ...]:
    box = shape.BoundingBox()
    return tuple(
        cq.Vector(x, y, z)
        for x in (box.xmin, box.xmax)
        for y in (box.ymin, box.ymax)
        for z in (box.zmin, box.zmax)
    )


def _through_limits(
    body: cq.Shape, origin: cq.Vector, direction: cq.Vector
) -> tuple[cq.Vector, float]:
    projections = [corner.dot(direction) for corner in _bbox_corners(body)]
    diagonal = body.BoundingBox().DiagonalLength
    margin = max(diagonal * 0.05, 1.0)
    start_scalar = min(projections) - margin
    end_scalar = max(projections) + margin
    origin_scalar = origin.dot(direction)
    start = origin + direction.multiply(start_scalar - origin_scalar)
    return start, end_scalar - start_scalar


def _extrusion_tool(
    graph: CADGraph,
    feature: ExtrusionFeature | PocketFeature,
    body: cq.Shape | None,
) -> tuple[cq.Shape, cq.Vector]:
    faces = _profiles(graph, feature.sketch_id, feature.profile_ids)
    direction = _unit(feature.direction, "extrusion direction")
    if isinstance(feature, PocketFeature):
        extent: str = feature.extent
        distance = float(feature.depth)
    else:
        extent = feature.extent
        distance = float(feature.distance or 0.0)

    tools: list[cq.Shape] = []
    for face in faces:
        start_face = face
        length = distance
        if extent == "symmetric":
            vector = direction.multiply(distance)
            start_face = face.translate(vector.multiply(-0.5))
        elif extent == "throughAll":
            if body is None:
                raise FeatureBuildFailure(
                    "through_all_without_body",
                    "throughAll requires an existing body",
                    "Use a finite base feature before a through-all cut.",
                )
            start, length = _through_limits(body, face.Center(), direction)
            start_face = face.translate(start - face.Center())
        elif extent == "toFace":
            raise FeatureBuildFailure(
                "to_face_requires_semantic_resolution",
                "toFace is resolved by the compiler before tool construction",
                "Select a resolved target face.",
            )
        if length <= 0:
            raise FeatureBuildFailure(
                "invalid_distance",
                "extrusion distance must be positive",
                "Set a positive feature distance.",
            )
        try:
            tools.append(cq.Solid.extrudeLinear(start_face, direction.multiply(length)))
        except Exception as exc:
            raise FeatureBuildFailure(
                "extrusion_failed",
                f"Open CASCADE failed to extrude the profile: {exc}",
                "Check profile validity, direction, distance, and body intersection.",
            ) from exc
    return _shape_from_solids(tools), direction


def _hole_cylinder(
    body: cq.Shape,
    position: cq.Vector,
    direction: cq.Vector,
    radius: float,
    hole_type: str,
    depth: float | None,
) -> cq.Solid:
    if hole_type == "through":
        start, height = _through_limits(body, position, direction)
    else:
        if depth is None or depth <= 0:
            raise FeatureBuildFailure(
                "invalid_hole_depth",
                "blind hole depth must be positive",
                "Set a positive depth smaller than the available material thickness.",
            )
        start, height = position, depth
    return cq.Solid.makeCylinder(radius, height, start, direction)


def _hole_tool(
    feature: HoleFeature | CounterboreFeature | CountersinkFeature,
    body: cq.Shape,
) -> tuple[cq.Shape, cq.Vector]:
    direction = _unit(feature.axis, "hole axis")
    position = _vector(feature.position)
    main = _hole_cylinder(
        body,
        position,
        direction,
        float(feature.diameter) / 2,
        feature.hole_type,
        float(feature.depth) if feature.depth is not None else None,
    )
    if isinstance(feature, CounterboreFeature):
        counterbore = cq.Solid.makeCylinder(
            float(feature.bore_diameter) / 2,
            float(feature.bore_depth),
            position,
            direction,
        )
        return main.fuse(counterbore), direction
    if isinstance(feature, CountersinkFeature):
        half_angle = math.radians(float(feature.sink_angle_deg)) / 2
        sink_depth = (
            (float(feature.sink_diameter) - float(feature.diameter)) / 2 / math.tan(half_angle)
        )
        sink = cq.Solid.makeCone(
            float(feature.sink_diameter) / 2,
            float(feature.diameter) / 2,
            sink_depth,
            position,
            direction,
        )
        return main.fuse(sink), direction
    return main, direction


def _revolution_tool(graph: CADGraph, feature: RevolutionFeature) -> tuple[cq.Shape, cq.Vector]:
    faces = _profiles(graph, feature.sketch_id, feature.profile_ids)
    direction = _unit(feature.axis.direction, "revolution axis")
    origin = _vector(feature.axis.origin)
    axis_end = origin + direction
    tools: list[cq.Shape] = []
    for face in faces:
        try:
            tools.append(
                cq.Solid.revolve(
                    face,
                    float(feature.angle_deg),
                    origin,
                    axis_end,
                )
            )
        except Exception as exc:
            raise FeatureBuildFailure(
                "revolution_failed",
                f"Open CASCADE failed to revolve the profile: {exc}",
                "Keep the profile on one side of a non-zero axis and use an angle in (0, 360].",
            ) from exc
    return _shape_from_solids(tools), direction


def _resolve_artifact(resolver: ArtifactResolver | None, artifact_id: str) -> Path:
    if resolver is None:
        raise FeatureBuildFailure(
            "artifact_resolver_missing",
            f"imported artifact {artifact_id!r} has no resolver",
            "Provide the trusted artifact resolver when compiling imported fallback geometry.",
        )
    try:
        raw = resolver(artifact_id) if callable(resolver) else resolver[artifact_id]
    except (KeyError, OSError, ValueError) as exc:
        raise FeatureBuildFailure(
            "artifact_missing",
            f"artifact {artifact_id!r} could not be resolved",
            "Restore the referenced immutable artifact.",
        ) from exc
    path = Path(raw)
    if not path.is_file():
        raise FeatureBuildFailure(
            "artifact_missing",
            f"artifact {artifact_id!r} does not exist at {path}",
            "Restore the referenced immutable artifact.",
        )
    return path


def _faceted_stl(path: Path) -> cq.Shape:
    loaded = trimesh.load_mesh(path, process=True)
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise FeatureBuildFailure(
            "invalid_imported_mesh",
            f"artifact {path.name} is not a non-empty triangle mesh",
            "Provide a watertight STL fallback mesh.",
        )
    if not loaded.is_watertight:
        raise FeatureBuildFailure(
            "invalid_imported_mesh",
            f"artifact {path.name} is not watertight",
            "Repair the mesh explicitly before creating a faceted fallback solid.",
        )
    faces: list[cq.Face] = []
    for indices in loaded.faces:
        points = [cq.Vector(*(float(item) for item in loaded.vertices[index])) for index in indices]
        edges = [
            cq.Edge.makeLine(points[0], points[1]),
            cq.Edge.makeLine(points[1], points[2]),
            cq.Edge.makeLine(points[2], points[0]),
        ]
        wire = cq.Wire.assembleEdges(edges)
        faces.append(cq.Face.makeFromWires(wire))
    try:
        shell = cq.Shell.makeShell(faces)
        return cq.Solid.makeSolid(shell)
    except Exception as exc:
        raise FeatureBuildFailure(
            "faceted_brep_failed",
            f"watertight mesh could not form a faceted B-Rep: {exc}",
            "Use the repaired watertight source or an imported STEP fallback.",
        ) from exc


def _imported_tool(
    feature: ImportedFacetedFeature,
    resolver: ArtifactResolver | None,
    units: str,
) -> cq.Shape:
    path = _resolve_artifact(resolver, feature.source_artifact_id)
    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha != feature.mesh_sha256:
        raise FeatureBuildFailure(
            "artifact_hash_mismatch",
            f"artifact {feature.source_artifact_id!r} SHA-256 does not match CADGraph",
            "Restore the exact immutable artifact or create a new feature version.",
        )
    if path.suffix.lower() in {".step", ".stp"}:
        return import_step_shape(path, units)
    if path.suffix.lower() == ".stl":
        return _faceted_stl(path)
    raise FeatureBuildFailure(
        "unsupported_imported_artifact",
        f"imported fallback does not support {path.suffix or 'extensionless'} files",
        "Use a validated STEP or watertight STL artifact.",
    )


def _apply_boolean(
    body: cq.Shape | None,
    tool: cq.Shape,
    mode: str,
    tolerance: float,
) -> cq.Shape:
    try:
        if mode == "base":
            if body is not None:
                raise FeatureBuildFailure(
                    "second_base_feature",
                    "a base feature cannot replace an existing body",
                    "Change the feature to additive or reorder it as the first active feature.",
                )
            result = tool
        elif mode == "additive":
            if body is None:
                raise FeatureBuildFailure(
                    "missing_base_body",
                    "additive feature requires an existing body",
                    "Create an active base feature first.",
                )
            result = body.fuse(tool).clean()
        elif mode == "subtractive":
            if body is None:
                raise FeatureBuildFailure(
                    "missing_base_body",
                    "subtractive feature requires an existing body",
                    "Create an active base feature first.",
                )
            result = body.cut(tool).clean()
        else:
            raise FeatureBuildFailure(
                "invalid_boolean_mode",
                f"unsupported boolean mode {mode!r}",
                "Use base, additive, or subtractive.",
            )
    except FeatureBuildFailure:
        raise
    except Exception as exc:
        raise FeatureBuildFailure(
            "boolean_failed",
            f"Open CASCADE boolean {mode} failed: {exc}",
            "Check feature/body intersection and reduce coincident or near-zero geometry.",
        ) from exc
    solid = _single_solid(result)
    if body is not None:
        before = float(body.Volume())
        after = float(solid.Volume())
        delta_tolerance = max(tolerance**3, abs(before) * 1e-12, 1e-12)
        if mode == "additive" and after <= before + delta_tolerance:
            raise FeatureBuildFailure(
                "boolean_no_effect",
                "additive feature did not add measurable material",
                "Move the feature so it intersects the body without being fully contained.",
            )
        if mode == "subtractive" and after >= before - delta_tolerance:
            raise FeatureBuildFailure(
                "boolean_no_effect",
                "subtractive feature did not remove measurable material",
                "Reverse the cut direction or move the profile/tool into the body.",
            )
    return solid


def _source_states(
    feature: Any,
    states: Mapping[str, _FeatureState],
) -> list[_FeatureState]:
    result: list[_FeatureState] = []
    for source_id in feature.source_feature_ids:
        state = states.get(source_id)
        if state is None:
            raise FeatureBuildFailure(
                "pattern_source_unavailable",
                f"source feature {source_id!r} has no reusable geometry",
                "Pattern or mirror an active earlier solid feature.",
            )
        result.append(state)
    return result


def _pattern_feature(
    feature: LinearPatternFeature | CircularPatternFeature,
    body: cq.Shape,
    states: Mapping[str, _FeatureState],
    tolerance: float,
) -> tuple[cq.Shape, cq.Shape, str, cq.Vector]:
    sources = _source_states(feature, states)
    modes = {source.mode for source in sources}
    if len(modes) != 1 or "base" in modes:
        raise FeatureBuildFailure(
            "mixed_pattern_modes",
            "pattern sources must share one additive or subtractive mode",
            "Create separate patterns for additive and subtractive source features.",
        )
    mode = modes.pop()
    instances: list[cq.Shape] = []
    if isinstance(feature, LinearPatternFeature):
        direction = _unit(feature.direction, "linear pattern direction")
        for index in range(1, feature.count):
            offset = direction.multiply(float(feature.spacing) * index)
            instances.extend(source.tool.translate(offset) for source in sources)
    else:
        direction = _unit(feature.axis.direction, "circular pattern axis")
        origin = _vector(feature.axis.origin)
        end = origin + direction
        increment = (
            float(feature.total_angle_deg) / feature.count
            if math.isclose(float(feature.total_angle_deg), 360.0, abs_tol=1e-12)
            else float(feature.total_angle_deg) / (feature.count - 1)
        )
        for index in range(1, feature.count):
            angle = increment * index
            instances.extend(source.tool.rotate(origin, end, angle) for source in sources)
    tool = _shape_from_solids(instances)
    result = _apply_boolean(body, tool, mode, tolerance)
    return result, tool, mode, direction


def _mirror_feature(
    feature: MirrorFeature,
    body: cq.Shape,
    states: Mapping[str, _FeatureState],
    tolerance: float,
    previous_feature_id: str | None,
) -> tuple[cq.Shape, cq.Shape, str, cq.Vector]:
    sources = _source_states(feature, states)
    modes = {source.mode for source in sources}
    if len(modes) != 1:
        raise FeatureBuildFailure(
            "mixed_mirror_modes",
            "mirror sources must share one boolean mode",
            "Mirror additive and subtractive source features separately.",
        )
    mode = modes.pop()
    normal = _unit(feature.plane.normal, "mirror plane normal")
    origin = _vector(feature.plane.origin)
    mirrored = [source.tool.mirror(normal, origin) for source in sources]
    tool = _shape_from_solids(mirrored)
    working_body: cq.Shape | None = body
    if not feature.keep_originals:
        if len(sources) != 1 or feature.source_feature_ids[0] != previous_feature_id:
            raise FeatureBuildFailure(
                "mirror_replace_requires_adjacent_source",
                "keepOriginals=false requires one immediately preceding source feature",
                "Move the mirror directly after its source or keep the original.",
            )
        working_body = sources[0].body_before
        if mode == "base":
            return _apply_boolean(None, tool, "base", tolerance), tool, "base", normal
    if mode == "base":
        mode = "additive"
    result = _apply_boolean(working_body, tool, mode, tolerance)
    return result, tool, mode, normal


def _finishing_feature(
    feature: ChamferFeature | FilletFeature,
    body: cq.Shape,
    registry: TopologyRegistry,
) -> tuple[cq.Shape, cq.Shape, str]:
    edges = [cast(cq.Edge, registry.require_shape(item, "edge")) for item in feature.target_edges]
    solid = _single_solid(body)
    try:
        if isinstance(feature, ChamferFeature):
            result = solid.chamfer(float(feature.width), None, edges)
        else:
            result = solid.fillet(float(feature.radius), edges)
    except Exception as exc:
        label = "chamfer" if isinstance(feature, ChamferFeature) else "fillet"
        raise FeatureBuildFailure(
            f"{label}_failed",
            f"Open CASCADE {label} failed: {exc}",
            "Reduce the width/radius and reselect edges on the current body.",
        ) from exc
    result = _single_solid(result)
    removed = body.cut(result).clean()
    return result, removed, "subtractive"


def _validation_tolerance(graph: CADGraph) -> float:
    # Feature validation should not create an excessively fine cached browser mesh.
    return max(
        float(graph.project_tolerance.linear_resolution),
        min(float(graph.project_tolerance.surface_deviation), 0.1),
    )


def _validate_feature_result(graph: CADGraph, shape: cq.Shape) -> ShapeValidation:
    validation = validate_shape(
        shape,
        linear_resolution=_validation_tolerance(graph),
        angular_tolerance=max(
            math.radians(float(graph.project_tolerance.angular_deviation_deg)),
            0.05,
        ),
    )
    if not validation.valid:
        raise FeatureBuildFailure(
            "invalid_brep",
            "; ".join(validation.errors),
            "Correct the current feature parameters; the previous valid result was preserved.",
        )
    return validation


def _compile_error(feature: Any, exc: Exception, last_valid: str | None) -> CompileError:
    if isinstance(exc, FeatureBuildFailure):
        code = exc.code
        recommendation = exc.recommendation
    else:
        code = "kernel_exception"
        recommendation = "Review feature parameters and referenced dependencies."
    return CompileError(
        code=code,
        feature_id=feature.id,
        feature_type=feature.operation,
        order=feature.order,
        parameters=feature.model_dump(mode="json", by_alias=True),
        dependencies=tuple(feature.dependencies),
        kernel_error=str(exc) or type(exc).__name__,
        last_valid_feature_id=last_valid,
        recommendation=recommendation,
    )


def compile_cadgraph(
    graph: CADGraph,
    artifact_resolver: ArtifactResolver | None = None,
    previous_topology: Mapping[str, ResolvedTopology | Mapping[str, Any]] | None = None,
) -> CompilationResult:
    """Compile a strict CADGraph in authored order, stopping at the first red feature gate."""

    registry = TopologyRegistry(graph.project_tolerance.linear_resolution, previous_topology)
    explicit_by_feature = {
        feature.id: [
            reference
            for reference in graph.semantic_topology
            if reference.producer_feature_id == feature.id
        ]
        for feature in graph.features
    }
    tolerance = max(float(graph.project_tolerance.linear_resolution), 1e-9)
    body: cq.Shape | None = None
    last_valid_feature_id: str | None = None
    states: dict[str, _FeatureState] = {}
    records: list[FeatureRecord] = []
    errors: list[CompileError] = []
    provenance: list[ProvenanceRecord] = []
    previous_feature_id: str | None = None

    for feature in graph.features:
        if feature.suppressed:
            records.append(
                FeatureRecord(
                    feature.id,
                    feature.operation,
                    feature.order,
                    "suppressed",
                    float(body.Volume()) if body is not None else None,
                    float(body.Volume()) if body is not None else None,
                    None,
                    (),
                    topology_hash(body, tolerance) if body is not None else None,
                )
            )
            continue
        before = body
        topology_before = {
            semantic_id: copy(record)
            for semantic_id, record in registry.records.items()
        }
        topology_issues_before = list(registry.issues)
        direction: cq.Vector | None = None
        tool: cq.Shape | None = None
        mode = "subtractive"
        try:
            if isinstance(feature, ExtrusionFeature):
                if feature.extent == "toFace":
                    if body is None or feature.target_face is None:
                        raise FeatureBuildFailure(
                            "to_face_target_missing",
                            "toFace extrusion has no existing target face",
                            "Select a resolved target face on an existing body.",
                        )
                    target = cast(cq.Face, registry.require_shape(feature.target_face, "face"))
                    direction = _unit(feature.direction, "extrusion direction")
                    faces = _profiles(graph, feature.sketch_id, feature.profile_ids)
                    distance = (target.Center() - faces[0].Center()).dot(direction)
                    if distance <= tolerance:
                        raise FeatureBuildFailure(
                            "to_face_behind_profile",
                            "target face is not ahead of the profile along the feature direction",
                            "Reverse the direction or select another target face.",
                        )
                    extrusion_data = feature.model_copy(
                        update={"extent": "blind", "distance": distance}
                    )
                    tool, direction = _extrusion_tool(graph, extrusion_data, body)
                else:
                    tool, direction = _extrusion_tool(graph, feature, body)
                mode = feature.boolean_mode
                body = _apply_boolean(body, tool, mode, tolerance)
            elif isinstance(feature, PocketFeature):
                if body is None:
                    raise FeatureBuildFailure(
                        "missing_base_body",
                        "pocket requires an existing body",
                        "Create a base first.",
                    )
                if feature.extent == "toFace":
                    if feature.target_face is None:
                        raise FeatureBuildFailure(
                            "to_face_target_missing",
                            "toFace pocket has no target face",
                            "Select a resolved target face.",
                        )
                    target = cast(cq.Face, registry.require_shape(feature.target_face, "face"))
                    direction = _unit(feature.direction, "pocket direction")
                    faces = _profiles(graph, feature.sketch_id, feature.profile_ids)
                    depth = (target.Center() - faces[0].Center()).dot(direction)
                    if depth <= tolerance:
                        raise FeatureBuildFailure(
                            "to_face_behind_profile",
                            "target face is not ahead of the pocket profile",
                            "Reverse the direction or select another target face.",
                        )
                    pocket_data = feature.model_copy(update={"extent": "blind", "depth": depth})
                    tool, direction = _extrusion_tool(graph, pocket_data, body)
                else:
                    tool, direction = _extrusion_tool(graph, feature, body)
                mode = "subtractive"
                body = _apply_boolean(body, tool, mode, tolerance)
            elif isinstance(feature, (HoleFeature, CounterboreFeature, CountersinkFeature)):
                if body is None:
                    raise FeatureBuildFailure(
                        "missing_base_body",
                        "hole requires an existing body",
                        "Create a base first.",
                    )
                tool, direction = _hole_tool(feature, body)
                mode = "subtractive"
                body = _apply_boolean(body, tool, mode, tolerance)
            elif isinstance(feature, RevolutionFeature):
                tool, direction = _revolution_tool(graph, feature)
                mode = feature.boolean_mode
                body = _apply_boolean(body, tool, mode, tolerance)
            elif isinstance(feature, (LinearPatternFeature, CircularPatternFeature)):
                if body is None:
                    raise FeatureBuildFailure(
                        "missing_base_body",
                        "pattern requires an existing body",
                        "Create a base first.",
                    )
                body, tool, mode, direction = _pattern_feature(feature, body, states, tolerance)
            elif isinstance(feature, MirrorFeature):
                if body is None:
                    raise FeatureBuildFailure(
                        "missing_base_body",
                        "mirror requires an existing body",
                        "Create a base first.",
                    )
                body, tool, mode, direction = _mirror_feature(
                    feature,
                    body,
                    states,
                    tolerance,
                    previous_feature_id,
                )
            elif isinstance(feature, (ChamferFeature, FilletFeature)):
                if body is None:
                    raise FeatureBuildFailure(
                        "missing_base_body",
                        "finishing feature requires an existing body",
                        "Create a base first.",
                    )
                body, tool, mode = _finishing_feature(feature, body, registry)
            elif isinstance(feature, ImportedFacetedFeature):
                tool = _imported_tool(feature, artifact_resolver, graph.units)
                mode = feature.boolean_mode
                body = _apply_boolean(body, tool, mode, tolerance)
            else:
                raise FeatureBuildFailure(
                    "unsupported_feature",
                    f"unsupported feature model {type(feature).__name__}",
                    "Use one of the operations supported by CADGraph 1.0.0.",
                )

            if body is None or tool is None:
                raise FeatureBuildFailure(
                    "empty_feature_result",
                    "feature did not produce a body and reusable tool",
                    "Check feature parameters and dependencies.",
                )
            body = _single_solid(body)
            validation = _validate_feature_result(graph, body)
            registry.remap_against(body)
            semantic_ids = registry.register_feature(
                feature,
                body,
                explicit_by_feature[feature.id],
                direction=direction,
            )
            state = _FeatureState(mode, tool, before, body)
            states[feature.id] = state
            last_valid_feature_id = feature.id
            previous_feature_id = feature.id
            records.append(
                FeatureRecord(
                    feature.id,
                    feature.operation,
                    feature.order,
                    "valid",
                    float(before.Volume()) if before is not None else None,
                    validation.volume,
                    validation,
                    semantic_ids,
                    topology_hash(body, tolerance),
                )
            )
            provenance.append(
                ProvenanceRecord(
                    feature_id=feature.id,
                    relation=f"boolean:{mode}",
                    source_kind=tool.ShapeType(),
                    source_descriptor=topology_hash(tool, tolerance),
                    result_kind=body.ShapeType(),
                    result_descriptor=topology_hash(body, tolerance),
                )
            )
        except Exception as exc:
            body = before
            registry.records = topology_before
            registry.issues = topology_issues_before
            errors.append(_compile_error(feature, exc, last_valid_feature_id))
            records.append(
                FeatureRecord(
                    feature.id,
                    feature.operation,
                    feature.order,
                    "failed",
                    float(before.Volume()) if before is not None else None,
                    None,
                    None,
                    (),
                    topology_hash(before, tolerance) if before is not None else None,
                )
            )
            break

    return CompilationResult(
        success=not errors and body is not None,
        shape=body,
        last_valid_feature_id=last_valid_feature_id,
        feature_records=records,
        errors=errors,
        topology=registry.snapshot(),
        topology_issues=list(registry.issues),
        provenance=provenance,
    )


__all__ = [
    "ArtifactResolver",
    "CompilationResult",
    "FeatureRecord",
    "compile_cadgraph",
]
