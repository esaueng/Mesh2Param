"""Explicit, replayable, non-destructive mesh repair operations."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol, cast

import numpy as np
import trimesh
from numpy.typing import NDArray

from .ingest import (
    DEFAULT_MESH_LIMITS,
    IngestedMesh,
    MeshDiagnostics,
    MeshFormat,
    MeshLimits,
    diagnose_mesh,
)

type RepairParameter = bool | int | float | str


class _FixNormals(Protocol):
    def __call__(self, mesh: trimesh.Trimesh, *, multibody: bool) -> object: ...


OperationName = Literal[
    "merge_duplicate_vertices",
    "remove_degenerate_faces",
    "remove_duplicate_faces",
    "remove_unreferenced_vertices",
    "orient_winding",
    "repair_normals",
    "keep_largest_component",
    "drop_tiny_components",
    "fill_small_holes",
]

DETERMINISTIC_OPERATION_TIMESTAMP = "1970-01-01T00:00:00Z"


def _camel_case_key(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class MeshRepairError(ValueError):
    """A fail-closed repair failure scoped to one explicit operation."""

    def __init__(self, code: str, operation: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.operation = operation


@dataclass(frozen=True, slots=True)
class RepairSettings:
    """Opt-in repair configuration; smoothing and decimation are intentionally absent."""

    merge_duplicate_vertices: bool = True
    merge_tolerance: float = 1e-8
    remove_degenerate_faces: bool = True
    degenerate_area_tolerance: float = 1e-18
    remove_duplicate_faces: bool = True
    remove_unreferenced_vertices: bool = True
    orient_winding: bool = True
    repair_normals: bool = True
    keep_largest_component: bool = False
    drop_tiny_components: bool = False
    tiny_component_area_ratio: float = 1e-4
    tiny_component_min_area: float = 0.0
    fill_small_holes: bool = False
    max_hole_edges: int = 8
    hole_planarity_tolerance: float = 1e-6

    def __post_init__(self) -> None:
        toggles = (
            self.merge_duplicate_vertices,
            self.remove_degenerate_faces,
            self.remove_duplicate_faces,
            self.remove_unreferenced_vertices,
            self.orient_winding,
            self.repair_normals,
            self.keep_largest_component,
            self.drop_tiny_components,
            self.fill_small_holes,
        )
        if not all(isinstance(value, bool) for value in toggles):
            raise ValueError("repair operation toggles must be boolean")
        positive = {
            "merge_tolerance": self.merge_tolerance,
            "hole_planarity_tolerance": self.hole_planarity_tolerance,
        }
        for name, value in positive.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        non_negative = {
            "degenerate_area_tolerance": self.degenerate_area_tolerance,
            "tiny_component_min_area": self.tiny_component_min_area,
        }
        for name, value in non_negative.items():
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not math.isfinite(self.tiny_component_area_ratio) or not (
            0 <= self.tiny_component_area_ratio < 1
        ):
            raise ValueError("tiny_component_area_ratio must be in [0, 1)")
        if (
            not isinstance(self.max_hole_edges, int)
            or isinstance(self.max_hole_edges, bool)
            or self.max_hole_edges < 3
        ):
            raise ValueError("max_hole_edges must be an integer of at least 3")

    def to_dict(self) -> dict[str, object]:
        return {
            "mergeDuplicateVertices": self.merge_duplicate_vertices,
            "mergeTolerance": self.merge_tolerance,
            "removeDegenerateFaces": self.remove_degenerate_faces,
            "degenerateAreaTolerance": self.degenerate_area_tolerance,
            "removeDuplicateFaces": self.remove_duplicate_faces,
            "removeUnreferencedVertices": self.remove_unreferenced_vertices,
            "orientWinding": self.orient_winding,
            "repairNormals": self.repair_normals,
            "keepLargestComponent": self.keep_largest_component,
            "dropTinyComponents": self.drop_tiny_components,
            "tinyComponentAreaRatio": self.tiny_component_area_ratio,
            "tinyComponentMinArea": self.tiny_component_min_area,
            "fillSmallHoles": self.fill_small_holes,
            "maxHoleEdges": self.max_hole_edges,
            "holePlanarityTolerance": self.hole_planarity_tolerance,
        }


DEFAULT_REPAIR_SETTINGS = RepairSettings()


@dataclass(frozen=True, slots=True)
class MeshStateMetrics:
    version_id: str
    vertex_count: int
    triangle_count: int
    connected_component_count: int
    surface_area: float
    closed_volume: float | None
    watertight: bool
    winding_consistent: bool
    degenerate_triangle_count: int
    duplicate_face_count: int
    non_manifold_edge_count: int
    open_boundary_edge_count: int
    open_boundary_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "versionId": self.version_id,
            "vertexCount": self.vertex_count,
            "triangleCount": self.triangle_count,
            "connectedComponentCount": self.connected_component_count,
            "surfaceArea": self.surface_area,
            "closedVolume": self.closed_volume,
            "watertight": self.watertight,
            "windingConsistent": self.winding_consistent,
            "degenerateTriangleCount": self.degenerate_triangle_count,
            "duplicateFaceCount": self.duplicate_face_count,
            "nonManifoldEdgeCount": self.non_manifold_edge_count,
            "openBoundaryEdgeCount": self.open_boundary_edge_count,
            "openBoundaryCount": self.open_boundary_count,
        }


@dataclass(frozen=True, slots=True)
class RepairOperation:
    id: str
    order: int
    operation: OperationName
    enabled: bool
    parameters: dict[str, RepairParameter]
    source_version_id: str
    result_version_id: str
    before: MeshStateMetrics
    after: MeshStateMetrics
    warnings: tuple[str, ...]
    reversible: bool
    timestamp: str

    @property
    def changed(self) -> bool:
        return self.source_version_id != self.result_version_id

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "order": self.order,
            "operation": self.operation,
            "enabled": self.enabled,
            "parameters": {_camel_case_key(key): value for key, value in self.parameters.items()},
            "sourceVersionId": self.source_version_id,
            "resultVersionId": self.result_version_id,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "warnings": list(self.warnings),
            "reversible": self.reversible,
            "timestamp": self.timestamp,
            "changed": self.changed,
        }


@dataclass(frozen=True, slots=True)
class RepairResult:
    source_id: str
    result_id: str
    source_sha256: str | None
    mesh: trimesh.Trimesh
    settings: RepairSettings
    operations: tuple[RepairOperation, ...]
    source_metrics: MeshStateMetrics
    result_metrics: MeshStateMetrics
    diagnostics: MeshDiagnostics
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def repaired_mesh(self) -> trimesh.Trimesh:
        return self.mesh

    def mesh_copy(self) -> trimesh.Trimesh:
        return self.mesh.copy()

    def to_dict(self) -> dict[str, object]:
        return {
            "sourceId": self.source_id,
            "resultId": self.result_id,
            "sourceSha256": self.source_sha256,
            "settings": self.settings.to_dict(),
            "operations": [operation.to_dict() for operation in self.operations],
            "sourceMetrics": self.source_metrics.to_dict(),
            "resultMetrics": self.result_metrics.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
            "warnings": list(self.warnings),
        }


def _vertices(mesh: trimesh.Trimesh) -> NDArray[np.float64]:
    return np.asarray(mesh.vertices, dtype=np.float64)


def _faces(mesh: trimesh.Trimesh) -> NDArray[np.int64]:
    return np.asarray(mesh.faces, dtype=np.int64)


def geometry_fingerprint(mesh: trimesh.Trimesh) -> str:
    """Hash canonical vertex/face arrays without changing geometry or winding."""

    vertices = _vertices(mesh)
    faces = _faces(mesh)
    vertex_order = np.lexsort(
        (
            np.arange(len(vertices), dtype=np.int64),
            vertices[:, 2],
            vertices[:, 1],
            vertices[:, 0],
        )
    )
    inverse = np.empty(len(vertices), dtype=np.int64)
    inverse[vertex_order] = np.arange(len(vertices), dtype=np.int64)
    remapped = inverse[faces]
    canonical_faces = np.empty_like(remapped)
    for index, face in enumerate(remapped):
        rotations = (
            (int(face[0]), int(face[1]), int(face[2])),
            (int(face[1]), int(face[2]), int(face[0])),
            (int(face[2]), int(face[0]), int(face[1])),
        )
        canonical_faces[index] = min(rotations)
    if len(canonical_faces):
        face_order = np.lexsort(
            (canonical_faces[:, 2], canonical_faces[:, 1], canonical_faces[:, 0])
        )
        canonical_faces = canonical_faces[face_order]

    digest = hashlib.sha256()
    digest.update(struct.pack("<QQ", len(vertices), len(faces)))
    digest.update(np.asarray(vertices[vertex_order], dtype="<f8").tobytes(order="C"))
    digest.update(np.asarray(canonical_faces, dtype="<i8").tobytes(order="C"))
    return digest.hexdigest()


def _version_id(mesh: trimesh.Trimesh) -> str:
    return f"mesh:{geometry_fingerprint(mesh)}"


def _metrics(
    mesh: trimesh.Trimesh,
    *,
    mesh_format: MeshFormat,
    limits: MeshLimits,
    version_id: str | None = None,
) -> MeshStateMetrics:
    diagnostic = diagnose_mesh(
        mesh,
        mesh_format=mesh_format,
        encoding="internal",
        byte_size=0,
        sha256=geometry_fingerprint(mesh),
        limits=limits,
    )
    return MeshStateMetrics(
        version_id=version_id or _version_id(mesh),
        vertex_count=diagnostic.raw_vertex_count,
        triangle_count=diagnostic.triangle_count,
        connected_component_count=diagnostic.connected_component_count,
        surface_area=diagnostic.surface_area,
        closed_volume=diagnostic.closed_volume,
        watertight=diagnostic.watertight,
        winding_consistent=diagnostic.winding_consistent,
        degenerate_triangle_count=diagnostic.degenerate_triangle_count,
        duplicate_face_count=diagnostic.duplicate_face_count,
        non_manifold_edge_count=diagnostic.non_manifold_edge_count,
        open_boundary_edge_count=diagnostic.open_boundary_edge_count,
        open_boundary_count=diagnostic.open_boundary_count,
    )


def _replace_geometry(
    source: trimesh.Trimesh,
    vertices: NDArray[np.float64],
    faces: NDArray[np.int64],
) -> trimesh.Trimesh:
    return trimesh.Trimesh(
        vertices=np.array(vertices, dtype=np.float64, copy=True),
        faces=np.array(faces, dtype=np.int64, copy=True),
        process=False,
        validate=False,
        metadata=dict(source.metadata),
    )


def _merge_vertices(
    mesh: trimesh.Trimesh, tolerance: float
) -> tuple[trimesh.Trimesh, tuple[str, ...]]:
    vertices = _vertices(mesh)
    faces = _faces(mesh)
    unique, exact_inverse = np.unique(vertices, axis=0, return_inverse=True)
    representative = np.empty(len(unique), dtype=np.int64)
    cells: dict[tuple[int, int, int], list[int]] = {}
    tolerance_squared = tolerance * tolerance
    offsets = tuple(itertools.product((-1, 0, 1), repeat=3))
    for index, point in enumerate(unique):
        cell = (
            math.floor(float(point[0]) / tolerance),
            math.floor(float(point[1]) / tolerance),
            math.floor(float(point[2]) / tolerance),
        )
        candidates: list[int] = []
        for offset in offsets:
            neighbor = (cell[0] + offset[0], cell[1] + offset[1], cell[2] + offset[2])
            candidates.extend(cells.get(neighbor, ()))
        chosen: int | None = None
        for candidate in sorted(candidates):
            delta = point - unique[candidate]
            if float(np.dot(delta, delta)) <= tolerance_squared:
                chosen = candidate
                break
        if chosen is None:
            chosen = index
            cells.setdefault(cell, []).append(index)
        representative[index] = chosen

    kept = np.flatnonzero(representative == np.arange(len(unique), dtype=np.int64))
    representative_to_new = np.full(len(unique), -1, dtype=np.int64)
    representative_to_new[kept] = np.arange(len(kept), dtype=np.int64)
    remap = representative_to_new[representative]
    merged_faces = remap[exact_inverse[faces]]
    merged = _replace_geometry(mesh, unique[kept], merged_faces)
    removed = len(vertices) - len(kept)
    warnings = () if removed == 0 else (f"Merged {removed} duplicate/near-duplicate vertices.",)
    return merged, warnings


def _remove_degenerate(
    mesh: trimesh.Trimesh, area_tolerance: float
) -> tuple[trimesh.Trimesh, tuple[str, ...]]:
    vertices = _vertices(mesh)
    faces = _faces(mesh)
    repeated = (
        (faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2]) | (faces[:, 2] == faces[:, 0])
    )
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) * 0.5
    keep = ~(repeated | (area <= area_tolerance))
    removed = int(np.count_nonzero(~keep))
    if removed == len(faces):
        raise MeshRepairError(
            "empty_result", "remove_degenerate_faces", "operation would remove every triangle"
        )
    repaired = _replace_geometry(mesh, vertices, faces[keep])
    warnings = () if removed == 0 else (f"Removed {removed} degenerate triangles.",)
    return repaired, warnings


def _remove_duplicate_faces(
    mesh: trimesh.Trimesh,
) -> tuple[trimesh.Trimesh, tuple[str, ...]]:
    vertices = _vertices(mesh)
    faces = _faces(mesh)
    canonical = np.sort(faces, axis=1)
    _, first = np.unique(canonical, axis=0, return_index=True)
    keep_indices = np.sort(first)
    removed = len(faces) - len(keep_indices)
    repaired = _replace_geometry(mesh, vertices, faces[keep_indices])
    warnings = () if removed == 0 else (f"Removed {removed} duplicate triangles.",)
    return repaired, warnings


def _remove_unreferenced(
    mesh: trimesh.Trimesh,
) -> tuple[trimesh.Trimesh, tuple[str, ...]]:
    vertices = _vertices(mesh)
    faces = _faces(mesh)
    used = np.unique(faces.reshape(-1))
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[used] = np.arange(len(used), dtype=np.int64)
    repaired = _replace_geometry(mesh, vertices[used], remap[faces])
    removed = len(vertices) - len(used)
    warnings = () if removed == 0 else (f"Removed {removed} unreferenced vertices.",)
    return repaired, warnings


def _orient_winding(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, tuple[str, ...]]:
    repaired = mesh.copy()
    fix_winding = cast(Callable[[trimesh.Trimesh], object], trimesh.repair.fix_winding)
    fix_winding(repaired)
    return repaired, ()


def _repair_normals(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, tuple[str, ...]]:
    repaired = mesh.copy()
    fix_normals = cast(_FixNormals, trimesh.repair.fix_normals)
    fix_normals(repaired, multibody=True)
    return repaired, ()


def _face_component_indices(mesh: trimesh.Trimesh) -> tuple[NDArray[np.int64], ...]:
    faces = _faces(mesh)
    if len(faces) == 0:
        return ()
    parent = np.arange(len(faces), dtype=np.int64)

    def find(index: int) -> int:
        while int(parent[index]) != index:
            parent[index] = parent[int(parent[index])]
            index = int(parent[index])
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    edge_owner: dict[tuple[int, int], int] = {}
    for face_index, face in enumerate(faces):
        for start, end in ((0, 1), (1, 2), (2, 0)):
            left, right = sorted((int(face[start]), int(face[end])))
            edge = (left, right)
            owner = edge_owner.setdefault(edge, face_index)
            union(owner, face_index)
    groups: dict[int, list[int]] = {}
    for face_index in range(len(faces)):
        groups.setdefault(find(face_index), []).append(face_index)
    return tuple(
        np.asarray(groups[root], dtype=np.int64)
        for root in sorted(groups, key=lambda item: groups[item][0])
    )


def _submesh(mesh: trimesh.Trimesh, face_indices: NDArray[np.int64]) -> trimesh.Trimesh:
    faces = _faces(mesh)[face_indices]
    vertices = _vertices(mesh)
    used = np.unique(faces.reshape(-1))
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[used] = np.arange(len(used), dtype=np.int64)
    return _replace_geometry(mesh, vertices[used], remap[faces])


def _component_area(mesh: trimesh.Trimesh, indices: NDArray[np.int64]) -> float:
    faces = _faces(mesh)[indices]
    vertices = _vertices(mesh)
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    return float(np.sum(np.linalg.norm(np.cross(b - a, c - a), axis=1)) * 0.5)


def _keep_largest(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, tuple[str, ...]]:
    components = _face_component_indices(mesh)
    if len(components) <= 1:
        return mesh.copy(), ()
    ranked: list[tuple[float, int, str, NDArray[np.int64]]] = []
    for indices in components:
        candidate = _submesh(mesh, indices)
        ranked.append(
            (_component_area(mesh, indices), len(indices), geometry_fingerprint(candidate), indices)
        )
    selected = min(ranked, key=lambda item: (-item[0], -item[1], item[2]))[3]
    repaired = _submesh(mesh, selected)
    dropped = len(components) - 1
    return repaired, (f"Dropped {dropped} non-largest connected components.",)


def _drop_tiny(
    mesh: trimesh.Trimesh,
    area_ratio: float,
    minimum_area: float,
) -> tuple[trimesh.Trimesh, tuple[str, ...]]:
    components = _face_component_indices(mesh)
    if len(components) <= 1:
        return mesh.copy(), ()
    areas = [_component_area(mesh, indices) for indices in components]
    threshold = max(sum(areas) * area_ratio, minimum_area)
    largest = max(range(len(components)), key=lambda index: (areas[index], len(components[index])))
    kept = [
        indices
        for index, indices in enumerate(components)
        if areas[index] >= threshold or index == largest
    ]
    if len(kept) == len(components):
        return mesh.copy(), ()
    selected = np.sort(np.concatenate(kept))
    repaired = _submesh(mesh, selected)
    return repaired, (f"Dropped {len(components) - len(kept)} tiny connected components.",)


def _boundary_loops(mesh: trimesh.Trimesh) -> tuple[tuple[tuple[int, ...], ...], tuple[str, ...]]:
    faces = _faces(mesh)
    occurrences: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for face in faces:
        for left, right in (
            (int(face[0]), int(face[1])),
            (int(face[1]), int(face[2])),
            (int(face[2]), int(face[0])),
        ):
            first, second = sorted((left, right))
            occurrences.setdefault((first, second), []).append((left, right))
    directed = [values[0] for values in occurrences.values() if len(values) == 1]
    adjacency: dict[int, set[int]] = {}
    for left, right in directed:
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    unseen = set(adjacency)
    loops: list[tuple[int, ...]] = []
    warnings: list[str] = []
    directed_set = set(directed)
    while unseen:
        seed = min(unseen)
        component: set[int] = set()
        stack = [seed]
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            unseen.discard(current)
            stack.extend(sorted(adjacency[current] - component, reverse=True))
        if any(len(adjacency[vertex] & component) != 2 for vertex in component):
            warnings.append("Skipped a branched or open boundary that is not a simple loop.")
            continue
        start = min(component)
        neighbors = sorted(adjacency[start] & component)
        next_vertex = next(
            (neighbor for neighbor in neighbors if (start, neighbor) in directed_set),
            neighbors[0],
        )
        ordered = [start]
        previous, current = start, next_vertex
        while current != start and len(ordered) <= len(component):
            ordered.append(current)
            candidates = sorted((adjacency[current] & component) - {previous})
            if not candidates:
                break
            previous, current = current, candidates[0]
        if current != start or len(ordered) != len(component):
            warnings.append("Skipped a boundary whose edges could not be ordered into one loop.")
            continue
        forward = sum(
            (ordered[index], ordered[(index + 1) % len(ordered)]) in directed_set
            for index in range(len(ordered))
        )
        if forward not in {0, len(ordered)}:
            warnings.append("Skipped a boundary with inconsistent local winding.")
            continue
        if forward == len(ordered):
            ordered = list(reversed(ordered))
        minimum_at = ordered.index(min(ordered))
        ordered = ordered[minimum_at:] + ordered[:minimum_at]
        loops.append(tuple(ordered))
    return tuple(sorted(loops)), tuple(warnings)


def _project_loop(
    points: NDArray[np.float64], planarity_tolerance: float
) -> NDArray[np.float64] | None:
    centered = points - np.mean(points, axis=0)
    _, _, basis = np.linalg.svd(centered, full_matrices=False)
    if basis.shape != (3, 3):
        return None
    normal = basis[-1]
    if float(np.max(np.abs(centered @ normal))) > planarity_tolerance:
        return None
    return np.asarray(centered @ basis[:2].T, dtype=np.float64)


def _point_in_triangle(
    point: NDArray[np.float64],
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    c: NDArray[np.float64],
    orientation: float,
    epsilon: float,
) -> bool:
    def cross(left: NDArray[np.float64], right: NDArray[np.float64]) -> float:
        return float(left[0] * right[1] - left[1] * right[0])

    ab = cross(b - a, point - a) * orientation
    bc = cross(c - b, point - b) * orientation
    ca = cross(a - c, point - c) * orientation
    return ab >= -epsilon and bc >= -epsilon and ca >= -epsilon


def _triangulate_loop(
    loop: tuple[int, ...], projected: NDArray[np.float64]
) -> tuple[tuple[int, int, int], ...] | None:
    signed_area = 0.5 * float(
        np.sum(
            projected[:, 0] * np.roll(projected[:, 1], -1)
            - projected[:, 1] * np.roll(projected[:, 0], -1)
        )
    )
    epsilon = max(float(np.ptp(projected, axis=0).max()) ** 2 * 1e-14, 1e-24)
    if abs(signed_area) <= epsilon:
        return None
    orientation = 1.0 if signed_area > 0 else -1.0
    remaining = list(range(len(loop)))
    triangles: list[tuple[int, int, int]] = []
    while len(remaining) > 3:
        clipped = False
        for cursor, current in enumerate(remaining):
            previous = remaining[cursor - 1]
            following = remaining[(cursor + 1) % len(remaining)]
            a, b, c = projected[previous], projected[current], projected[following]
            cross = float((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
            if cross * orientation <= epsilon:
                continue
            if any(
                _point_in_triangle(projected[index], a, b, c, orientation, epsilon)
                for index in remaining
                if index not in {previous, current, following}
            ):
                continue
            triangles.append((loop[previous], loop[current], loop[following]))
            del remaining[cursor]
            clipped = True
            break
        if not clipped:
            return None
    triangles.append((loop[remaining[0]], loop[remaining[1]], loop[remaining[2]]))
    return tuple(triangles)


def _fill_small_holes(
    mesh: trimesh.Trimesh,
    max_edges: int,
    planarity_tolerance: float,
) -> tuple[trimesh.Trimesh, tuple[str, ...]]:
    loops, boundary_warnings = _boundary_loops(mesh)
    vertices = _vertices(mesh)
    additions: list[tuple[int, int, int]] = []
    warnings = list(boundary_warnings)
    filled = 0
    for loop in loops:
        if len(loop) > max_edges:
            warnings.append(
                f"Skipped boundary with {len(loop)} edges (configured maximum is {max_edges})."
            )
            continue
        projected = _project_loop(vertices[np.asarray(loop, dtype=np.int64)], planarity_tolerance)
        if projected is None:
            warnings.append("Skipped a non-planar small boundary.")
            continue
        triangles = _triangulate_loop(loop, projected)
        if triangles is None:
            warnings.append("Skipped a small boundary that could not be triangulated safely.")
            continue
        additions.extend(triangles)
        filled += 1
    if not additions:
        return mesh.copy(), tuple(warnings)
    faces = np.vstack((_faces(mesh), np.asarray(additions, dtype=np.int64)))
    repaired = _replace_geometry(mesh, vertices, faces)
    warnings.append(f"Filled {filled} small boundary holes with {len(additions)} triangles.")
    return repaired, tuple(warnings)


def _validate_timestamp(timestamp: str) -> str:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("operation timestamp must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError("operation timestamp must include a timezone")
    return timestamp


def _operation_id(
    order: int,
    name: OperationName,
    enabled: bool,
    parameters: dict[str, RepairParameter],
    source_version_id: str,
    result_version_id: str,
) -> str:
    encoded = json.dumps(
        {
            "order": order,
            "operation": name,
            "enabled": enabled,
            "parameters": parameters,
            "source": source_version_id,
            "result": result_version_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"repair-op:{order:02d}:{name}:{hashlib.sha256(encoded).hexdigest()[:16]}"


def repair_mesh(
    source: IngestedMesh | trimesh.Trimesh,
    settings: RepairSettings = DEFAULT_REPAIR_SETTINGS,
    *,
    limits: MeshLimits = DEFAULT_MESH_LIMITS,
    operation_timestamp: str = DETERMINISTIC_OPERATION_TIMESTAMP,
) -> RepairResult:
    """Repair a copy of ``source`` and record every ordered operation.

    The fixed default timestamp makes engine-only runs byte-for-byte
    deterministic.  Service callers can inject the real timezone-aware job
    timestamp without affecting geometry or version IDs.
    """

    timestamp = _validate_timestamp(operation_timestamp)
    if isinstance(source, IngestedMesh):
        source_mesh = source.mesh
        source_id = source.source_id
        source_sha256: str | None = source.metadata.sha256
        mesh_format = source.metadata.format
        encoding = source.metadata.encoding
        byte_size = source.metadata.byte_size
    elif isinstance(source, trimesh.Trimesh):
        source_mesh = source
        source_id = _version_id(source)
        source_sha256 = None
        mesh_format = "stl"
        encoding = "internal"
        byte_size = 0
    else:
        raise TypeError(f"expected IngestedMesh or trimesh.Trimesh, got {type(source).__name__}")
    source_fingerprint = geometry_fingerprint(source_mesh)
    current_fingerprint = source_fingerprint
    working = source_mesh.copy()
    current_version = source_id
    current_metrics = _metrics(
        working, mesh_format=mesh_format, limits=limits, version_id=current_version
    )
    source_metrics = current_metrics
    records: list[RepairOperation] = []
    all_warnings: list[str] = []

    operations: tuple[
        tuple[
            OperationName,
            bool,
            dict[str, RepairParameter],
        ],
        ...,
    ] = (
        (
            "merge_duplicate_vertices",
            settings.merge_duplicate_vertices,
            {"tolerance": settings.merge_tolerance},
        ),
        (
            "remove_degenerate_faces",
            settings.remove_degenerate_faces,
            {"area_tolerance": settings.degenerate_area_tolerance},
        ),
        ("remove_duplicate_faces", settings.remove_duplicate_faces, {}),
        ("remove_unreferenced_vertices", settings.remove_unreferenced_vertices, {}),
        ("orient_winding", settings.orient_winding, {}),
        ("repair_normals", settings.repair_normals, {"multibody": True}),
        ("keep_largest_component", settings.keep_largest_component, {"measure": "surface_area"}),
        (
            "drop_tiny_components",
            settings.drop_tiny_components,
            {
                "area_ratio": settings.tiny_component_area_ratio,
                "minimum_area": settings.tiny_component_min_area,
            },
        ),
        (
            "fill_small_holes",
            settings.fill_small_holes,
            {
                "max_boundary_edges": settings.max_hole_edges,
                "planarity_tolerance": settings.hole_planarity_tolerance,
            },
        ),
    )

    for order, (name, enabled, parameters) in enumerate(operations, start=1):
        before = current_metrics
        warnings: tuple[str, ...] = ()
        try:
            if enabled:
                if name == "merge_duplicate_vertices":
                    working, warnings = _merge_vertices(working, settings.merge_tolerance)
                elif name == "remove_degenerate_faces":
                    working, warnings = _remove_degenerate(
                        working, settings.degenerate_area_tolerance
                    )
                elif name == "remove_duplicate_faces":
                    working, warnings = _remove_duplicate_faces(working)
                elif name == "remove_unreferenced_vertices":
                    working, warnings = _remove_unreferenced(working)
                elif name == "orient_winding":
                    working, warnings = _orient_winding(working)
                elif name == "repair_normals":
                    working, warnings = _repair_normals(working)
                elif name == "keep_largest_component":
                    working, warnings = _keep_largest(working)
                elif name == "drop_tiny_components":
                    if settings.keep_largest_component:
                        warnings = (
                            "No additional component filtering was needed after keep-largest.",
                        )
                    else:
                        working, warnings = _drop_tiny(
                            working,
                            settings.tiny_component_area_ratio,
                            settings.tiny_component_min_area,
                        )
                else:
                    working, warnings = _fill_small_holes(
                        working,
                        settings.max_hole_edges,
                        settings.hole_planarity_tolerance,
                    )
        except MeshRepairError:
            raise
        except Exception as exc:
            raise MeshRepairError(
                "operation_failed", name, f"{name} failed without producing a result: {exc}"
            ) from exc

        next_fingerprint = geometry_fingerprint(working)
        result_version = (
            current_version
            if next_fingerprint == current_fingerprint
            else f"mesh:{next_fingerprint}"
        )
        after = _metrics(
            working,
            mesh_format=mesh_format,
            limits=limits,
            version_id=result_version,
        )
        record = RepairOperation(
            id=_operation_id(order, name, enabled, parameters, current_version, result_version),
            order=order,
            operation=name,
            enabled=enabled,
            parameters=dict(parameters),
            source_version_id=current_version,
            result_version_id=result_version,
            before=before,
            after=after,
            warnings=warnings,
            reversible=True,
            timestamp=timestamp,
        )
        records.append(record)
        all_warnings.extend(warnings)
        current_version = result_version
        current_fingerprint = next_fingerprint
        current_metrics = after

    if geometry_fingerprint(source_mesh) != source_fingerprint:
        raise MeshRepairError(
            "source_mutated", "repair", "source mesh changed during non-destructive repair"
        )
    diagnostics = diagnose_mesh(
        working,
        mesh_format=mesh_format,
        encoding=encoding,
        byte_size=byte_size,
        sha256=source_sha256 or source_fingerprint,
        limits=limits,
    )
    return RepairResult(
        source_id=source_id,
        result_id=current_version,
        source_sha256=source_sha256,
        mesh=working,
        settings=settings,
        operations=tuple(records),
        source_metrics=source_metrics,
        result_metrics=current_metrics,
        diagnostics=diagnostics,
        warnings=tuple(all_warnings),
    )


def repair(
    source: IngestedMesh | trimesh.Trimesh,
    settings: RepairSettings = DEFAULT_REPAIR_SETTINGS,
    *,
    limits: MeshLimits = DEFAULT_MESH_LIMITS,
    operation_timestamp: str = DETERMINISTIC_OPERATION_TIMESTAMP,
) -> RepairResult:
    """Compatibility alias for :func:`repair_mesh`."""

    return repair_mesh(
        source,
        settings,
        limits=limits,
        operation_timestamp=operation_timestamp,
    )


__all__ = [
    "DEFAULT_REPAIR_SETTINGS",
    "DETERMINISTIC_OPERATION_TIMESTAMP",
    "MeshRepairError",
    "MeshStateMetrics",
    "RepairOperation",
    "RepairResult",
    "RepairSettings",
    "geometry_fingerprint",
    "repair",
    "repair_mesh",
]
