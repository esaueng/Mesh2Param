"""Semantic topology and deterministic analytic shape descriptors.

Raw Open CASCADE identity, enumeration order, selector strings, and hash codes
are deliberately not persisted.  Runtime subshapes are tracked with kernel
history when available and otherwise matched only when an analytic descriptor
has exactly one candidate.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from .errors import SemanticResolutionFailure, TopologyIssue


def _q(value: float, resolution: float) -> int:
    return round(float(value) / resolution)


def _cq_vector(value: cq.Vector, resolution: float) -> tuple[int, int, int]:
    return (_q(value.x, resolution), _q(value.y, resolution), _q(value.z, resolution))


def _native_vector(value: Any, resolution: float) -> tuple[int, int, int]:
    return (
        _q(value.X(), resolution),
        _q(value.Y(), resolution),
        _q(value.Z(), resolution),
    )


def _canonical_direction(value: Any, resolution: float) -> tuple[int, int, int]:
    components = [float(value.X()), float(value.Y()), float(value.Z())]
    epsilon = max(resolution, 1e-12)
    for component in components:
        if abs(component) > epsilon:
            if component < 0:
                components = [-item for item in components]
            break
    return tuple(_q(item, resolution) for item in components)  # type: ignore[return-value]


def _bbox(shape: cq.Shape, resolution: float) -> tuple[int, int, int, int, int, int]:
    # CadQuery's BoundingBox() may include cached tessellation deflection.  The
    # geometry-only box stays stable before and after browser tessellation.
    native = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, native, False, False)
    return tuple(_q(item, resolution) for item in native.Get())  # type: ignore[return-value]


def _axis_descriptor(axis: Any, resolution: float) -> dict[str, Any]:
    direction = axis.Direction()
    raw_direction = (
        float(direction.X()),
        float(direction.Y()),
        float(direction.Z()),
    )
    location = axis.Location()
    raw_location = (
        float(location.X()),
        float(location.Y()),
        float(location.Z()),
    )
    along = sum(a * b for a, b in zip(raw_location, raw_direction, strict=True))
    closest = tuple(a - along * b for a, b in zip(raw_location, raw_direction, strict=True))
    return {
        "direction": _canonical_direction(direction, resolution),
        "closestOrigin": tuple(_q(item, resolution) for item in closest),
    }


def edge_descriptor(edge: cq.Edge, resolution: float) -> dict[str, Any]:
    """Return an order-independent descriptor for a B-Rep edge."""

    kind = str(edge.geomType())
    endpoints = sorted(
        (_cq_vector(edge.startPoint(), resolution), _cq_vector(edge.endPoint(), resolution))
    )
    result: dict[str, Any] = {
        "kind": kind,
        "length": _q(edge.Length(), resolution),
        "center": _cq_vector(edge.Center(), resolution),
        "endpoints": endpoints,
        "bbox": _bbox(edge, resolution),
    }
    adaptor = BRepAdaptor_Curve(edge.wrapped)
    try:
        if kind == "LINE":
            result["direction"] = _canonical_direction(adaptor.Line().Direction(), resolution)
        elif kind == "CIRCLE":
            circle = adaptor.Circle()
            result.update(
                radius=_q(circle.Radius(), resolution),
                axis=_axis_descriptor(circle.Axis(), resolution),
            )
        elif kind == "ELLIPSE":
            ellipse = adaptor.Ellipse()
            result.update(
                majorRadius=_q(ellipse.MajorRadius(), resolution),
                minorRadius=_q(ellipse.MinorRadius(), resolution),
                axis=_axis_descriptor(ellipse.Axis(), resolution),
            )
    except (RuntimeError, ValueError):
        # The base descriptor still differentiates unsupported analytic curves.
        result["analyticParametersUnavailable"] = True
    return result


def _face_orientation(face: cq.Face, axis: Any, sample: cq.Vector) -> int:
    normal = face.normalAt(sample)
    axis_point = cq.Vector(axis.Location().X(), axis.Location().Y(), axis.Location().Z())
    axis_direction = cq.Vector(axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z())
    radial = sample - (
        axis_point + axis_direction.multiply((sample - axis_point).dot(axis_direction))
    )
    return 1 if normal.dot(radial) >= 0 else -1


def edge_face_ancestor_map(owner: cq.Shape) -> TopTools_IndexedDataMapOfShapeListOfShape:
    """Map every edge of ``owner`` to the faces that contain it, built in a single pass.

    ``cq.Edge.ancestors`` rebuilds this map from scratch on every call, so computing an
    adjacency descriptor per edge is O(edges * subshapes).  Building it once and reusing it
    keeps face descriptors linear without changing their contents.
    """

    shape_map = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(owner.wrapped, TopAbs_EDGE, TopAbs_FACE, shape_map)
    return shape_map


def face_descriptor(
    face: cq.Face,
    resolution: float,
    owner: cq.Shape | None = None,
    edge_face_map: TopTools_IndexedDataMapOfShapeListOfShape | None = None,
) -> dict[str, Any]:
    """Return an analytic, boundary, orientation and adjacency face descriptor.

    When ``owner`` is given, adjacency to neighbouring faces is derived from ``edge_face_map``
    (built once by the caller for the whole shape) or, if omitted, from a map built once here.
    """

    kind = str(face.geomType())
    boundaries = [edge_descriptor(edge, resolution) for edge in face.Edges()]
    boundaries.sort(key=_canonical_json)
    result: dict[str, Any] = {
        "kind": kind,
        "area": _q(face.Area(), resolution * resolution),
        "center": _cq_vector(face.Center(), resolution),
        "bbox": _bbox(face, resolution),
        "wireCount": len(face.Wires()),
        "innerWireCount": len(face.innerWires()),
        "boundary": boundaries,
    }
    adaptor = BRepAdaptor_Surface(face.wrapped)
    try:
        if kind == "PLANE":
            normal = face.normalAt()
            result["orientedNormal"] = _cq_vector(normal, resolution)
            result["orientedOffset"] = _q(normal.dot(face.Center()), resolution)
        elif kind == "CYLINDER":
            cylinder = adaptor.Cylinder()
            u = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
            v = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
            sample = face.positionAt(u, v)
            result.update(
                radius=_q(cylinder.Radius(), resolution),
                axis=_axis_descriptor(cylinder.Axis(), resolution),
                orientation=_face_orientation(face, cylinder.Axis(), sample),
            )
        elif kind == "CONE":
            cone = adaptor.Cone()
            u = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
            v = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
            sample = face.positionAt(u, v)
            result.update(
                # STEP may reverse cone parameterization; magnitude is invariant.
                semiAngle=_q(abs(cone.SemiAngle()), resolution),
                referenceRadius=_q(cone.RefRadius(), resolution),
                axis=_axis_descriptor(cone.Axis(), resolution),
                orientation=_face_orientation(face, cone.Axis(), sample),
            )
        elif kind == "SPHERE":
            sphere = adaptor.Sphere()
            result.update(
                radius=_q(sphere.Radius(), resolution),
                sphereCenter=_native_vector(sphere.Location(), resolution),
            )
        elif kind == "TORUS":
            torus = adaptor.Torus()
            result.update(
                majorRadius=_q(torus.MajorRadius(), resolution),
                minorRadius=_q(torus.MinorRadius(), resolution),
                axis=_axis_descriptor(torus.Axis(), resolution),
            )
    except (RuntimeError, ValueError):
        result["analyticParametersUnavailable"] = True

    if owner is not None:
        if edge_face_map is None:
            edge_face_map = edge_face_ancestor_map(owner)
        adjacency: list[tuple[str, ...]] = []
        for edge in face.Edges():
            try:
                neighbors = [
                    cq.Shape.cast(item) for item in edge_face_map.FindFromKey(edge.wrapped)
                ]
                kinds = sorted(
                    str(neighbor.geomType())
                    for neighbor in neighbors
                    if not neighbor.isSame(face)
                )
            except (RuntimeError, ValueError):
                kinds = []
            adjacency.append(tuple(kinds))
        result["adjacentFaceKindsByBoundary"] = sorted(adjacency)
    return result


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def descriptor_hash(descriptor: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(descriptor).encode("utf-8")).hexdigest()


def shape_descriptor(
    shape: cq.Shape,
    resolution: float,
    owner: cq.Shape | None = None,
) -> dict[str, Any]:
    shape_type = shape.ShapeType().lower()
    if shape_type == "edge":
        return {"shapeType": "edge", **edge_descriptor(cq.Edge(shape.wrapped), resolution)}
    if shape_type == "face":
        return {
            "shapeType": "face",
            **face_descriptor(cq.Face(shape.wrapped), resolution, owner),
        }
    if shape_type in {"solid", "compsolid", "compound"}:
        edge_face_map = edge_face_ancestor_map(shape)
        face_hashes = sorted(
            descriptor_hash(face_descriptor(face, resolution, shape, edge_face_map))
            for face in shape.Faces()
        )
        return {
            "shapeType": shape_type,
            "volume": _q(shape.Volume(), resolution**3),
            "area": _q(shape.Area(), resolution**2),
            "bbox": _bbox(shape, resolution),
            "faceDescriptors": face_hashes,
        }
    return {"shapeType": shape_type, "bbox": _bbox(shape, resolution)}


def topology_descriptor(shape: cq.Shape, resolution: float) -> dict[str, Any]:
    edge_face_map = edge_face_ancestor_map(shape)
    faces = [face_descriptor(face, resolution, shape, edge_face_map) for face in shape.Faces()]
    edges = [edge_descriptor(edge, resolution) for edge in shape.Edges()]
    faces.sort(key=_canonical_json)
    edges.sort(key=_canonical_json)
    return {"faces": faces, "edges": edges}


def topology_hash(shape: cq.Shape, resolution: float) -> str:
    return descriptor_hash(topology_descriptor(shape, resolution))


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    feature_id: str
    relation: str
    source_kind: str
    source_descriptor: str
    result_kind: str | None
    result_descriptor: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "featureId": self.feature_id,
            "relation": self.relation,
            "sourceKind": self.source_kind,
            "sourceDescriptor": self.source_descriptor,
            "resultKind": self.result_kind,
            "resultDescriptor": self.result_descriptor,
        }


@dataclass(slots=True)
class ResolvedTopology:
    semantic_id: str
    kind: str
    producer_feature_id: str
    role: str
    generated_from: tuple[str, ...]
    status: str
    descriptor: dict[str, Any] | None = None
    descriptor_hash: str | None = None
    previous_descriptor_hash: str | None = None
    provenance: tuple[str, ...] = ()
    shape: cq.Shape | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "semanticId": self.semantic_id,
            "kind": self.kind,
            "producerFeatureId": self.producer_feature_id,
            "role": self.role,
            "generatedFrom": list(self.generated_from),
            "status": self.status,
            "descriptor": self.descriptor,
            "descriptorHash": self.descriptor_hash,
            "previousDescriptorHash": self.previous_descriptor_hash,
            "provenance": list(self.provenance),
        }


def _normalize_role(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", ".", value.lower()).strip(".")


def _same_shape(left: cq.Shape, right: cq.Shape) -> bool:
    try:
        return bool(left.isSame(right))
    except (RuntimeError, ValueError):
        return False


def _subshapes(shape: cq.Shape, kind: str) -> list[cq.Shape]:
    if kind == "edge":
        return list(shape.Edges())
    if kind == "face":
        return list(shape.Faces())
    if kind == "solid":
        return list(shape.Solids())
    return []


class TopologyRegistry:
    """Runtime semantic reference registry with explicit unresolved states."""

    def __init__(
        self,
        resolution: float,
        previous: Mapping[str, ResolvedTopology | Mapping[str, Any]] | None = None,
    ) -> None:
        self.resolution = max(float(resolution), 1e-9)
        self.records: dict[str, ResolvedTopology] = {}
        self.issues: list[TopologyIssue] = []
        self._previous = previous or {}

    def _record(
        self,
        semantic_id: str,
        kind: str,
        producer_feature_id: str,
        role: str,
        generated_from: Sequence[str],
        shape: cq.Shape | None,
        provenance: Sequence[str],
        descriptor_override: Mapping[str, Any] | None = None,
    ) -> ResolvedTopology:
        previous = self._previous.get(semantic_id)
        previous_hash: str | None = None
        if isinstance(previous, ResolvedTopology):
            previous_hash = previous.descriptor_hash
        elif isinstance(previous, Mapping):
            raw_hash = previous.get("descriptorHash", previous.get("descriptor_hash"))
            previous_hash = str(raw_hash) if raw_hash else None
        descriptor = (
            dict(descriptor_override)
            if descriptor_override is not None
            else shape_descriptor(shape, self.resolution)
            if shape is not None
            else None
        )
        record = ResolvedTopology(
            semantic_id=semantic_id,
            kind=kind,
            producer_feature_id=producer_feature_id,
            role=role,
            generated_from=tuple(generated_from),
            status="resolved" if shape is not None else "unresolved",
            descriptor=descriptor,
            descriptor_hash=descriptor_hash(descriptor) if descriptor is not None else None,
            previous_descriptor_hash=previous_hash,
            provenance=tuple(provenance),
            shape=shape,
        )
        self.records[semantic_id] = record
        return record

    def remap_against(self, result: cq.Shape, history_builders: Iterable[Any] = ()) -> None:
        """Remap existing records through OCCT history or one exact descriptor match."""

        builders = tuple(history_builders)
        for record in self.records.values():
            old = record.shape
            if old is None or record.kind not in {"solid", "face", "edge"}:
                continue
            if record.kind == "solid":
                solids = result.Solids()
                if len(solids) == 1:
                    candidate: cq.Shape = solids[0]
                    record.shape = candidate
                    record.status = "resolved"
                    # Source-bound descriptors are intentionally lightweight at the imported
                    # feature boundary. Once a later feature remaps that solid, its identity must
                    # describe the new kernel result rather than the original mesh artifact.
                    record.descriptor = shape_descriptor(candidate, self.resolution)
                    record.descriptor_hash = descriptor_hash(record.descriptor)
                continue

            current = _subshapes(result, record.kind)
            preserved = [candidate for candidate in current if _same_shape(candidate, old)]
            if len(preserved) == 1:
                record.shape = preserved[0]
                record.descriptor = shape_descriptor(preserved[0], self.resolution, result)
                record.descriptor_hash = descriptor_hash(record.descriptor)
                record.status = "resolved"
                continue

            history_candidates: list[cq.Shape] = []
            for builder in builders:
                for method_name in ("Modified", "Generated"):
                    method = getattr(builder, method_name, None)
                    if method is None:
                        continue
                    try:
                        native_items = method(old.wrapped)
                        for native in native_items:
                            candidate = cq.Shape.cast(native)
                            if candidate.ShapeType().lower() == record.kind and any(
                                _same_shape(candidate, item) for item in current
                            ):
                                history_candidates.append(candidate)
                    except (RuntimeError, ValueError, TypeError):
                        continue
            unique_history: list[cq.Shape] = []
            for candidate in history_candidates:
                if not any(_same_shape(candidate, item) for item in unique_history):
                    unique_history.append(candidate)
            if len(unique_history) == 1:
                candidate = unique_history[0]
                record.shape = candidate
                record.descriptor = shape_descriptor(candidate, self.resolution, result)
                record.descriptor_hash = descriptor_hash(record.descriptor)
                record.status = "resolved"
                record.provenance = (*record.provenance, "kernelHistory")
                continue

            old_hash = record.descriptor_hash
            exact = []
            if old_hash is not None:
                for candidate in current:
                    candidate_descriptor = shape_descriptor(candidate, self.resolution, result)
                    if descriptor_hash(candidate_descriptor) == old_hash:
                        exact.append((candidate, candidate_descriptor))
            if len(exact) == 1:
                record.shape, record.descriptor = exact[0]
                record.descriptor_hash = old_hash
                record.status = "resolved"
                record.provenance = (*record.provenance, "uniqueDescriptor")
                continue

            record.shape = None
            record.status = "unresolved"
            issue = TopologyIssue(
                semantic_id=record.semantic_id,
                producer_feature_id=record.producer_feature_id,
                message=(
                    "kernel history did not produce one matching subshape"
                    if not unique_history
                    else f"kernel history produced {len(unique_history)} candidates"
                ),
            )
            if not any(item.semantic_id == record.semantic_id for item in self.issues):
                self.issues.append(issue)

    def register_feature(
        self,
        feature: Any,
        result: cq.Shape,
        explicit_references: Sequence[Any],
        candidates: Mapping[str, Sequence[cq.Shape]] | None = None,
        direction: cq.Vector | None = None,
        *,
        faceted_mesh_sha256: str | None = None,
        faceted_sewing_tolerance: float | None = None,
        faceted_units: str | None = None,
    ) -> tuple[str, ...]:
        """Register automatic and contract-declared semantic topology outputs."""

        candidate_map = {
            _normalize_role(key): list(value) for key, value in (candidates or {}).items()
        }
        explicit_by_id = {item.id: item for item in explicit_references}
        registered: list[str] = []
        faceted_descriptor = (
            {
                "shapeType": "solid",
                "meshSha256": faceted_mesh_sha256,
                "sewingTolerance": faceted_sewing_tolerance,
                "units": faceted_units,
            }
            if faceted_mesh_sha256 is not None
            else None
        )

        solid_id = f"{feature.id}.solid"
        if solid_id not in explicit_by_id:
            self._record(
                solid_id,
                "solid",
                feature.id,
                "resultSolid",
                feature.dependencies,
                result.Solids()[0] if len(result.Solids()) == 1 else None,
                ("featureResult",),
                descriptor_override=faceted_descriptor,
            )
            registered.append(solid_id)

        subshape_groups = (
            ()
            if faceted_mesh_sha256 is not None
            else (("face", result.Faces()), ("edge", result.Edges()))
        )
        for kind, subitems in subshape_groups:
            ordered = sorted(
                subitems,
                key=lambda item: _canonical_json(shape_descriptor(item, self.resolution, result)),
            )
            for index, item in enumerate(ordered, 1):
                semantic_id = f"{feature.id}.{kind}.{index}"
                if semantic_id in explicit_by_id:
                    continue
                self._record(
                    semantic_id,
                    kind,
                    feature.id,
                    f"analytic{kind.title()}.{index}",
                    feature.dependencies,
                    item,
                    ("analyticDescriptor",),
                )
                registered.append(semantic_id)

        for reference in explicit_references:
            selected = self._select_reference(
                reference,
                result,
                candidate_map,
                direction,
            )
            record = self._record(
                reference.id,
                reference.kind,
                reference.producer_feature_id,
                reference.role,
                reference.generated_from,
                selected,
                ("declaredRole",),
                descriptor_override=(
                    faceted_descriptor
                    if faceted_descriptor is not None and reference.kind == "solid"
                    else None
                ),
            )
            registered.append(reference.id)
            if record.status != "resolved":
                self.issues.append(
                    TopologyIssue(
                        semantic_id=reference.id,
                        producer_feature_id=feature.id,
                        message=f"role {reference.role!r} did not resolve uniquely",
                    )
                )

        unresolved_outputs = [
            semantic_id
            for semantic_id in feature.semantic_outputs
            if semantic_id not in self.records or self.records[semantic_id].status != "resolved"
        ]
        if unresolved_outputs:
            raise SemanticResolutionFailure(
                unresolved_outputs[0],
                "the producing feature did not yield exactly one matching subshape",
            )
        return tuple(registered)

    def _select_reference(
        self,
        reference: Any,
        result: cq.Shape,
        candidates: Mapping[str, list[cq.Shape]],
        direction: cq.Vector | None,
    ) -> cq.Shape | None:
        kind = reference.kind
        if kind == "solid":
            solids = result.Solids()
            return solids[0] if len(solids) == 1 else None
        if kind not in {"face", "edge"}:
            return None

        role = _normalize_role(reference.role)
        selected = list(candidates.get(role, []))
        converted: list[cq.Shape] = []
        for item in selected:
            item_kind = item.ShapeType().lower()
            if item_kind == kind:
                converted.append(item)
            elif kind == "edge" and item_kind == "face":
                converted.extend(item.Edges())
        selected = converted

        all_items = _subshapes(result, kind)
        if not selected and kind == "face" and direction is not None:
            if any(token in role for token in ("top", "cap", "end")):
                projections = [item.Center().dot(direction) for item in all_items]
                if projections:
                    extreme = max(projections)
                    selected = [
                        item
                        for item, projection in zip(all_items, projections, strict=True)
                        if math.isclose(projection, extreme, abs_tol=self.resolution)
                    ]
            elif any(token in role for token in ("bottom", "base", "floor", "start")):
                projections = [item.Center().dot(direction) for item in all_items]
                if projections:
                    extreme = min(projections)
                    selected = [
                        item
                        for item, projection in zip(all_items, projections, strict=True)
                        if math.isclose(projection, extreme, abs_tol=self.resolution)
                    ]

        index_match = re.search(r"(?:profileedge|edge|face)\.?([0-9]+)$", role)
        if index_match is None:
            index_match = re.search(rf"{kind}\.([0-9]+)$", _normalize_role(reference.id))
        if index_match is not None:
            ordered = sorted(
                selected or all_items,
                key=lambda item: _canonical_json(shape_descriptor(item, self.resolution, result)),
            )
            index = int(index_match.group(1)) - 1
            return ordered[index] if 0 <= index < len(ordered) else None
        if len(selected) == 1:
            return selected[0]
        return None

    def require_shape(self, semantic_id: str, expected_kind: str) -> cq.Shape:
        record = self.records.get(semantic_id)
        if record is None:
            raise SemanticResolutionFailure(semantic_id, "the ID has never been produced")
        if record.kind != expected_kind:
            raise SemanticResolutionFailure(
                semantic_id,
                f"expected {expected_kind}, but the reference declares {record.kind}",
            )
        if record.status != "resolved" or record.shape is None:
            raise SemanticResolutionFailure(semantic_id, "the prior subshape no longer resolves")
        return record.shape

    def snapshot(self) -> dict[str, ResolvedTopology]:
        return dict(self.records)


__all__ = [
    "ProvenanceRecord",
    "ResolvedTopology",
    "TopologyRegistry",
    "descriptor_hash",
    "edge_descriptor",
    "face_descriptor",
    "shape_descriptor",
    "topology_descriptor",
    "topology_hash",
]
