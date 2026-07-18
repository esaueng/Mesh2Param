"""Bounded shallow cap-detail detection and explicit functional suppression."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely.ops import triangulate

from .sections import SectionStack


@dataclass(frozen=True, slots=True)
class DetailSuppressionSettings:
    minimum_depth_mm: float = 0.05
    support_plane_tolerance_mm: float = 0.03
    constant_depth_tolerance_mm: float = 0.03
    maximum_depth_fraction: float = 0.1
    maximum_footprint_area_fraction: float = 0.15
    maximum_volume_fraction: float = 0.01
    maximum_regions: int = 8
    maximum_source_triangle_ids: int = 2048

    def validate(self) -> None:
        positive = (
            self.minimum_depth_mm,
            self.support_plane_tolerance_mm,
            self.constant_depth_tolerance_mm,
            self.maximum_depth_fraction,
            self.maximum_footprint_area_fraction,
            self.maximum_volume_fraction,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("detail suppression tolerances and fractions must be positive")
        if self.maximum_depth_fraction >= 0.5:
            raise ValueError("shallow-detail depth fraction must be below 0.5")
        if self.maximum_footprint_area_fraction >= 1 or self.maximum_volume_fraction >= 1:
            raise ValueError("detail suppression fractions must be below 1")
        if self.maximum_regions < 1 or self.maximum_source_triangle_ids < 1:
            raise ValueError("detail suppression bounds must be positive")


@dataclass(frozen=True, slots=True)
class DetailDiagnostic:
    code: str
    message: str
    measured: dict[str, float | int | str] = field(default_factory=dict)
    source_triangle_ids: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "measured": dict(sorted(self.measured.items())),
            "sourceTriangleIds": list(self.source_triangle_ids),
        }


@dataclass(frozen=True, slots=True)
class SuppressedRegion:
    id: str
    kind: Literal["embossedCapDetail"]
    cap_side: Literal["lower", "upper"]
    support_offset_mm: float
    support_origin_mm: tuple[float, float, float]
    support_normal: tuple[float, float, float]
    boundary_vertex_ids: tuple[int, ...]
    boundary_points_mm: tuple[tuple[float, float, float], ...]
    boundary_points_2d_mm: tuple[tuple[float, float], ...]
    source_triangle_ids: tuple[int, ...]
    footprint_area_mm2: float
    depth_mm: float
    measured_volume_mm3: float
    exposed_area_mm2: float
    footprint_area_fraction: float
    volume_fraction: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "capSide": self.cap_side,
            "supportPlane": {
                "originMm": list(self.support_origin_mm),
                "normal": list(self.support_normal),
                "offsetMm": self.support_offset_mm,
            },
            "boundaryVertexIds": list(self.boundary_vertex_ids),
            "boundaryPointsMm": [list(point) for point in self.boundary_points_mm],
            "sourceTriangleIds": list(self.source_triangle_ids),
            "footprintAreaMm2": self.footprint_area_mm2,
            "depthMm": self.depth_mm,
            "measuredVolumeMm3": self.measured_volume_mm3,
            "exposedAreaMm2": self.exposed_area_mm2,
            "footprintAreaFraction": self.footprint_area_fraction,
            "volumeFraction": self.volume_fraction,
        }


@dataclass(frozen=True, slots=True)
class DetailSuppressionAnalysis:
    mode: Literal["functional", "full"]
    regions: tuple[SuppressedRegion, ...]
    diagnostics: tuple[DetailDiagnostic, ...] = ()

    @property
    def source_triangle_ids(self) -> tuple[int, ...]:
        return tuple(
            sorted(
                triangle_id for region in self.regions for triangle_id in region.source_triangle_ids
            )
        )

    @property
    def measured_volume_mm3(self) -> float:
        return sum(region.measured_volume_mm3 for region in self.regions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "regions": [region.to_dict() for region in self.regions],
            "suppressedTriangleCount": len(self.source_triangle_ids),
            "measuredVolumeMm3": self.measured_volume_mm3,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def _connected_face_components(
    mesh: trimesh.Trimesh, selected: np.ndarray
) -> tuple[tuple[int, ...], ...]:
    selected_set = {int(value) for value in selected}
    adjacency: dict[int, list[int]] = {value: [] for value in selected_set}
    for left, right in np.asarray(mesh.face_adjacency, dtype=np.int64):
        left_id, right_id = int(left), int(right)
        if left_id in selected_set and right_id in selected_set:
            adjacency[left_id].append(right_id)
            adjacency[right_id].append(left_id)
    components: list[tuple[int, ...]] = []
    remaining = set(selected_set)
    while remaining:
        seed = min(remaining)
        stack = [seed]
        component: list[int] = []
        remaining.remove(seed)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency[current], reverse=True):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
        components.append(tuple(sorted(component)))
    return tuple(components)


def _support_loop(
    mesh: trimesh.Trimesh,
    component: tuple[int, ...],
    offsets: np.ndarray,
    support_offset: float,
    section_stack: SectionStack,
    settings: DetailSuppressionSettings,
    cap_side: Literal["lower", "upper"],
) -> tuple[tuple[int, ...], np.ndarray, Polygon]:
    counts: dict[tuple[int, int], int] = {}
    for face_id in component:
        face = np.asarray(mesh.faces[face_id], dtype=np.int64)
        for first, second in zip(face, np.roll(face, -1), strict=True):
            ordered = sorted((int(first), int(second)))
            edge = (ordered[0], ordered[1])
            counts[edge] = counts.get(edge, 0) + 1
    support_edges = [
        edge
        for edge, count in counts.items()
        if count == 1
        and abs(float(offsets[edge[0]]) - support_offset) <= settings.support_plane_tolerance_mm
        and abs(float(offsets[edge[1]]) - support_offset) <= settings.support_plane_tolerance_mm
    ]
    neighbors: dict[int, list[int]] = {}
    for first, second in support_edges:
        neighbors.setdefault(first, []).append(second)
        neighbors.setdefault(second, []).append(first)
    if len(neighbors) < 3 or any(len(values) != 2 for values in neighbors.values()):
        raise ValueError("detail support boundary is not one closed manifold loop")
    projected_by_id = {
        vertex_id: section_stack.frame.project(
            np.asarray((mesh.vertices[vertex_id],), dtype=np.float64)
        )[0]
        for vertex_id in neighbors
    }
    start = min(
        neighbors,
        key=lambda vertex_id: (
            float(projected_by_id[vertex_id][0]),
            float(projected_by_id[vertex_id][1]),
            vertex_id,
        ),
    )
    candidates: list[tuple[int, ...]] = []
    for first_neighbor in sorted(neighbors[start]):
        ordered = [start]
        previous, current = start, first_neighbor
        while current != start:
            if current in ordered or len(ordered) > len(neighbors):
                raise ValueError("detail support boundary traversal did not close")
            ordered.append(current)
            following = [value for value in neighbors[current] if value != previous]
            if len(following) != 1:
                raise ValueError("detail support boundary branches")
            previous, current = current, following[0]
        if len(ordered) != len(neighbors):
            raise ValueError("detail support boundary has disconnected edges")
        candidates.append(tuple(ordered))
    ordered_ids = min(
        candidates,
        key=lambda values: tuple(
            (
                round(float(projected_by_id[value][0]), 9),
                round(float(projected_by_id[value][1]), 9),
            )
            for value in values
        ),
    )
    points_2d = np.asarray([projected_by_id[value] for value in ordered_ids])
    polygon = Polygon(points_2d)
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError("detail support boundary does not form a valid positive-area polygon")
    want_counterclockwise = cap_side == "upper"
    signed_twice_area = float(
        np.sum(
            points_2d[:, 0] * np.roll(points_2d[:, 1], -1)
            - np.roll(points_2d[:, 0], -1) * points_2d[:, 1]
        )
    )
    if (signed_twice_area > 0) != want_counterclockwise:
        ordered_ids = tuple(reversed(ordered_ids))
        points_2d = np.asarray([projected_by_id[value] for value in ordered_ids])
        polygon = Polygon(points_2d)
    return ordered_ids, points_2d, polygon


def analyze_shallow_cap_details(
    mesh: trimesh.Trimesh,
    section_stack: SectionStack,
    settings: DetailSuppressionSettings | None = None,
) -> DetailSuppressionAnalysis:
    """Declare bounded constant-depth material beyond the primary cap planes."""

    settings = settings or DetailSuppressionSettings()
    settings.validate()
    axis = np.asarray(section_stack.axis, dtype=np.float64)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    offsets = vertices @ axis
    face_offsets = offsets[faces]
    cap_area = abs(section_stack.reference_slice.loops[0].signed_area_mm2) - sum(
        abs(loop.signed_area_mm2) for loop in section_stack.reference_slice.loops[1:]
    )
    source_volume = abs(float(mesh.volume))
    extent = section_stack.primary_extent_mm
    regions: list[SuppressedRegion] = []
    diagnostics: list[DetailDiagnostic] = []
    cap_cases: tuple[tuple[Literal["lower", "upper"], float, np.ndarray], ...] = (
        (
            "lower",
            section_stack.cap_offsets_mm[0],
            np.flatnonzero(
                np.min(face_offsets, axis=1)
                < section_stack.cap_offsets_mm[0] - settings.minimum_depth_mm
            ),
        ),
        (
            "upper",
            section_stack.cap_offsets_mm[1],
            np.flatnonzero(
                np.max(face_offsets, axis=1)
                > section_stack.cap_offsets_mm[1] + settings.minimum_depth_mm
            ),
        ),
    )
    for cap_side, support_offset, selected in cap_cases:
        for component in _connected_face_components(mesh, selected):
            component_ids = np.asarray(component, dtype=np.int64)
            component_vertices = np.unique(faces[component_ids].reshape(-1))
            component_offsets = offsets[component_vertices]
            extreme = (
                float(np.min(component_offsets))
                if cap_side == "lower"
                else float(np.max(component_offsets))
            )
            depth = abs(extreme - support_offset)
            far = component_offsets[
                np.abs(component_offsets - support_offset) > settings.support_plane_tolerance_mm
            ]
            code: str | None = None
            message = ""
            if depth > settings.maximum_depth_fraction * extent:
                code, message = (
                    "detail-depth-limit",
                    "cap-attached material exceeds the shallow-detail depth fraction",
                )
            elif (
                len(far) == 0
                or np.max(np.abs(far - extreme)) > settings.constant_depth_tolerance_mm
            ):
                code, message = (
                    "nonconstant-detail-depth",
                    "cap-attached material does not have one bounded constant depth",
                )
            try:
                boundary_ids, points_2d, polygon = _support_loop(
                    mesh,
                    component,
                    offsets,
                    support_offset,
                    section_stack,
                    settings,
                    cap_side,
                )
            except ValueError as exc:
                boundary_ids, points_2d, polygon = (), np.empty((0, 2)), Polygon()
                code, message = "invalid-detail-boundary", str(exc)
            footprint_area = float(polygon.area) if not polygon.is_empty else 0.0
            measured_volume = footprint_area * depth
            area_fraction = footprint_area / cap_area if cap_area > 0 else float("inf")
            volume_fraction = measured_volume / source_volume if source_volume > 0 else float("inf")
            if code is None and area_fraction > settings.maximum_footprint_area_fraction:
                code, message = (
                    "detail-area-limit",
                    "cap-attached material exceeds the footprint-area fraction",
                )
            if code is None and volume_fraction > settings.maximum_volume_fraction:
                code, message = (
                    "detail-volume-limit",
                    "cap-attached material exceeds the volume fraction",
                )
            if len(component) > settings.maximum_source_triangle_ids:
                code, message = (
                    "detail-evidence-limit",
                    "cap-attached detail exceeds the triangle evidence bound",
                )
            if code is not None:
                diagnostics.append(
                    DetailDiagnostic(
                        code,
                        message,
                        {
                            "depthMm": depth,
                            "footprintAreaMm2": footprint_area,
                            "footprintAreaFraction": area_fraction,
                            "volumeFraction": volume_fraction,
                        },
                        component,
                    )
                )
                continue
            projected_triangle_vertices = section_stack.frame.project(
                vertices[faces[component_ids].reshape(-1)]
            )
            buffered = polygon.buffer(settings.support_plane_tolerance_mm)
            if not all(buffered.covers(Point(point)) for point in projected_triangle_vertices):
                diagnostics.append(
                    DetailDiagnostic(
                        "detail-outside-declared-region",
                        "a suppressed triangle projects outside its declared footprint",
                        source_triangle_ids=component,
                    )
                )
                continue
            normal = axis if cap_side == "upper" else -axis
            support_origin = axis * support_offset
            support_origin_tuple = (
                float(support_origin[0]),
                float(support_origin[1]),
                float(support_origin[2]),
            )
            normal_tuple = (float(normal[0]), float(normal[1]), float(normal[2]))
            regions.append(
                SuppressedRegion(
                    f"suppressed-region.{len(regions) + 1}",
                    "embossedCapDetail",
                    cap_side,
                    float(support_offset),
                    support_origin_tuple,
                    normal_tuple,
                    boundary_ids,
                    tuple(
                        (
                            float(vertices[vertex_id][0]),
                            float(vertices[vertex_id][1]),
                            float(vertices[vertex_id][2]),
                        )
                        for vertex_id in boundary_ids
                    ),
                    tuple((float(point[0]), float(point[1])) for point in points_2d),
                    component,
                    footprint_area,
                    depth,
                    measured_volume,
                    float(np.sum(mesh.area_faces[component_ids])),
                    area_fraction,
                    volume_fraction,
                )
            )
    if len(regions) > settings.maximum_regions:
        return DetailSuppressionAnalysis(
            "functional",
            (),
            (
                DetailDiagnostic(
                    "detail-region-limit",
                    f"detected {len(regions)} shallow regions; limit is {settings.maximum_regions}",
                    {"regionCount": len(regions)},
                ),
            ),
        )
    regions.sort(key=lambda region: (region.cap_side, region.boundary_points_2d_mm, region.id))
    regions = [
        SuppressedRegion(
            f"suppressed-region.{index}",
            region.kind,
            region.cap_side,
            region.support_offset_mm,
            region.support_origin_mm,
            region.support_normal,
            region.boundary_vertex_ids,
            region.boundary_points_mm,
            region.boundary_points_2d_mm,
            region.source_triangle_ids,
            region.footprint_area_mm2,
            region.depth_mm,
            region.measured_volume_mm3,
            region.exposed_area_mm2,
            region.footprint_area_fraction,
            region.volume_fraction,
        )
        for index, region in enumerate(regions, 1)
    ]
    return DetailSuppressionAnalysis("functional", tuple(regions), tuple(diagnostics))


def build_functional_reference_mesh(
    mesh: trimesh.Trimesh,
    analysis: DetailSuppressionAnalysis,
) -> trimesh.Trimesh:
    """Remove every declared emboss and close its support footprint exactly."""

    if analysis.diagnostics:
        raise ValueError("cannot build a functional reference from rejected detail evidence")
    suppressed = set(analysis.source_triangle_ids)
    retained = [
        tuple(int(value) for value in face)
        for index, face in enumerate(np.asarray(mesh.faces, dtype=np.int64))
        if index not in suppressed
    ]
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    for region in analysis.regions:
        points = np.asarray(region.boundary_points_2d_mm, dtype=np.float64)
        polygon = Polygon(points)
        for triangle in triangulate(polygon):
            if not polygon.covers(triangle.representative_point()):
                continue
            coordinates = np.asarray(triangle.exterior.coords[:-1], dtype=np.float64)
            local_indices: list[int] = []
            for coordinate in coordinates:
                distances = np.linalg.norm(points - coordinate, axis=1)
                local_index = int(np.argmin(distances))
                if float(distances[local_index]) > 1e-8:
                    raise ValueError("support triangulation introduced an unbound vertex")
                local_indices.append(local_index)
            face = [region.boundary_vertex_ids[index] for index in local_indices]
            normal = np.cross(
                vertices[face[1]] - vertices[face[0]], vertices[face[2]] - vertices[face[0]]
            )
            if float(np.dot(normal, np.asarray(region.support_normal))) < 0:
                face[1], face[2] = face[2], face[1]
            retained.append(tuple(face))
    result = trimesh.Trimesh(
        vertices=vertices.copy(),
        faces=np.asarray(retained, dtype=np.int64),
        process=False,
        validate=False,
    )
    result.remove_unreferenced_vertices()
    if not result.is_watertight or not result.is_winding_consistent:
        raise ValueError("functional suppression did not produce a closed consistently wound mesh")
    return result


__all__ = [
    "DetailDiagnostic",
    "DetailSuppressionAnalysis",
    "DetailSuppressionSettings",
    "SuppressedRegion",
    "analyze_shallow_cap_details",
    "build_functional_reference_mesh",
]
