"""Harmonic square parameterization of one disk-like chart (Milestone 1).

Maps a four-cornered disk-like triangulated region onto the unit square: the
four boundary chains go to the square edges by normalized arc length and the
interior solves a positive-weight harmonic system (Floater mean-value
weights), which guarantees an injective embedding for a convex boundary.
Folds and excessive distortion are rejected, never repaired silently.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import splu


class ChartParameterizationError(ValueError):
    """A chart that cannot be parameterized safely; callers must not fit it."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def detect_rectangle_corners(
    vertices: np.ndarray,
    boundary_loop: np.ndarray,
    *,
    minimum_turn_deg: float = 45.0,
) -> np.ndarray:
    """Positions (indices into the loop) of exactly four sharp boundary turns."""

    loop = np.asarray(boundary_loop, dtype=np.int64)
    if len(loop) < 4:
        raise ChartParameterizationError(
            "chart_boundary_too_short", "chart boundary has fewer than four vertices"
        )
    points = vertices[loop]
    incoming = points - np.roll(points, 1, axis=0)
    outgoing = np.roll(points, -1, axis=0) - points
    incoming_norm = np.linalg.norm(incoming, axis=1)
    outgoing_norm = np.linalg.norm(outgoing, axis=1)
    if np.any(incoming_norm <= 0.0) or np.any(outgoing_norm <= 0.0):
        raise ChartParameterizationError(
            "chart_boundary_degenerate", "chart boundary contains zero-length edges"
        )
    cosine = np.einsum("ij,ij->i", incoming, outgoing) / (incoming_norm * outgoing_norm)
    turn_deg = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
    sharp = np.flatnonzero(turn_deg >= minimum_turn_deg)
    if len(sharp) != 4:
        raise ChartParameterizationError(
            "chart_corner_count",
            f"expected exactly 4 sharp boundary corners, found {len(sharp)} "
            f"(threshold {minimum_turn_deg} degrees)",
        )
    return sharp


@dataclass(frozen=True, slots=True)
class ChartParameterization:
    uv: np.ndarray = field(repr=False)
    boundary_loop: np.ndarray = field(repr=False)
    corner_loop_positions: tuple[int, int, int, int]
    flipped_triangle_count: int
    minimum_uv_area_ratio: float
    maximum_stretch: float
    mean_area_distortion: float

    @property
    def corner_vertex_ids(self) -> tuple[int, int, int, int]:
        loop = self.boundary_loop
        a, b, c, d = self.corner_loop_positions
        return int(loop[a]), int(loop[b]), int(loop[c]), int(loop[d])

    def to_dict(self) -> dict[str, Any]:
        return {
            "vertexCount": len(self.uv),
            "boundaryVertexCount": len(self.boundary_loop),
            "cornerVertexIds": list(self.corner_vertex_ids),
            "flippedTriangleCount": self.flipped_triangle_count,
            "minimumUvAreaRatio": self.minimum_uv_area_ratio,
            "maximumStretch": self.maximum_stretch,
            "meanAreaDistortion": self.mean_area_distortion,
        }


def _boundary_square_uv(
    vertices: np.ndarray,
    loop: np.ndarray,
    corner_positions: np.ndarray,
) -> np.ndarray:
    """Assign square-edge UVs to the boundary loop, chain by chain."""

    count = len(loop)
    # Square corners in chain order: (0,0) -> (1,0) -> (1,1) -> (0,1).
    square = np.asarray([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    uv = np.zeros((count, 2))
    for chain in range(4):
        start = int(corner_positions[chain])
        end = int(corner_positions[(chain + 1) % 4])
        if end <= start:
            end += count
        positions = np.arange(start, end + 1) % count
        points = vertices[loop[positions]]
        segment = np.linalg.norm(np.diff(points, axis=0), axis=1)
        total = float(segment.sum())
        if total <= 0.0:
            raise ChartParameterizationError(
                "chart_boundary_degenerate", "a boundary chain has zero length"
            )
        fraction = np.concatenate([[0.0], np.cumsum(segment)]) / total
        source = square[chain]
        target = square[(chain + 1) % 4]
        uv[positions] = source + fraction[:, None] * (target - source)
    return uv


def _triangle_uv_metrics(
    vertices: np.ndarray, faces: np.ndarray, uv: np.ndarray
) -> tuple[int, float, float, float]:
    """Fold count, minimum signed-area ratio, max stretch, mean area distortion."""

    uv_edges_1 = uv[faces[:, 1]] - uv[faces[:, 0]]
    uv_edges_2 = uv[faces[:, 2]] - uv[faces[:, 0]]
    signed_area = 0.5 * (uv_edges_1[:, 0] * uv_edges_2[:, 1] - uv_edges_1[:, 1] * uv_edges_2[:, 0])
    orientation = 1.0 if signed_area.sum() >= 0.0 else -1.0
    oriented = orientation * signed_area
    flipped = int(np.count_nonzero(oriented <= 0.0))

    edges_1 = vertices[faces[:, 1]] - vertices[faces[:, 0]]
    edges_2 = vertices[faces[:, 2]] - vertices[faces[:, 0]]
    surface_area = 0.5 * np.linalg.norm(np.cross(edges_1, edges_2), axis=1)
    total_surface = float(surface_area.sum())
    total_uv = float(np.abs(signed_area).sum())
    if total_surface <= 0.0 or total_uv <= 0.0:
        raise ChartParameterizationError(
            "chart_degenerate_area", "chart surface or UV area is degenerate"
        )
    area_ratio = (np.abs(signed_area) / total_uv) / np.maximum(surface_area / total_surface, 1e-300)
    minimum_ratio = float(area_ratio.min())
    mean_distortion = float(
        np.average(
            np.maximum(area_ratio, 1.0 / np.maximum(area_ratio, 1e-300)), weights=surface_area
        )
    )

    # First fundamental form of the UV -> 3-D map per triangle: solve the 2x2
    # UV edge matrix against the 3-D edges, then take singular values.
    determinant = uv_edges_1[:, 0] * uv_edges_2[:, 1] - uv_edges_1[:, 1] * uv_edges_2[:, 0]
    safe = np.where(np.abs(determinant) < 1e-300, 1.0, determinant)
    inv_11 = uv_edges_2[:, 1] / safe
    inv_12 = -uv_edges_2[:, 0] / safe
    inv_21 = -uv_edges_1[:, 1] / safe
    inv_22 = uv_edges_1[:, 0] / safe
    jacobian_u = edges_1 * inv_11[:, None] + edges_2 * inv_21[:, None]
    jacobian_v = edges_1 * inv_12[:, None] + edges_2 * inv_22[:, None]
    e = np.einsum("ij,ij->i", jacobian_u, jacobian_u)
    f = np.einsum("ij,ij->i", jacobian_u, jacobian_v)
    g = np.einsum("ij,ij->i", jacobian_v, jacobian_v)
    trace = e + g
    root = np.sqrt(np.maximum((e - g) ** 2 + 4.0 * f**2, 0.0))
    sigma_max = np.sqrt(np.maximum((trace + root) / 2.0, 0.0))
    maximum_stretch = float(sigma_max.max())
    return flipped, minimum_ratio, maximum_stretch, mean_distortion


def _mean_value_weights(vertices: np.ndarray, faces: np.ndarray, count: int) -> csr_matrix:
    """Floater mean-value edge weights: positive and geometry-aware.

    Positive weights preserve the convex-boundary injectivity guarantee of the
    Tutte map while making the interior solution respect edge lengths and
    angles, which keeps UV distortion low on irregular triangulations.
    """

    rows: list[np.ndarray] = []
    columns: list[np.ndarray] = []
    data: list[np.ndarray] = []
    for apex, near, far in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
        origin = vertices[faces[:, apex]]
        toward_near = vertices[faces[:, near]] - origin
        toward_far = vertices[faces[:, far]] - origin
        length_near = np.linalg.norm(toward_near, axis=1)
        length_far = np.linalg.norm(toward_far, axis=1)
        safe = np.maximum(length_near * length_far, 1e-300)
        cosine = np.clip(np.einsum("ij,ij->i", toward_near, toward_far) / safe, -1.0, 1.0)
        half_tangent = np.tan(np.minimum(np.arccos(cosine), np.pi - 1e-9) / 2.0)
        rows.append(faces[:, apex])
        columns.append(faces[:, near])
        data.append(half_tangent / np.maximum(length_near, 1e-300))
        rows.append(faces[:, apex])
        columns.append(faces[:, far])
        data.append(half_tangent / np.maximum(length_far, 1e-300))
    return coo_matrix(
        (np.concatenate(data), (np.concatenate(rows), np.concatenate(columns))),
        shape=(count, count),
    ).tocsr()


def harmonic_square_parameterization(
    vertices: np.ndarray,
    faces: np.ndarray,
    boundary_loop: np.ndarray,
    *,
    corner_loop_positions: np.ndarray | None = None,
    minimum_turn_deg: float = 45.0,
    maximum_stretch_limit: float = 1e6,
) -> ChartParameterization:
    """Tutte-weight harmonic map of a disk-like chart onto the unit square."""

    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    loop = np.asarray(boundary_loop, dtype=np.int64)
    count = len(vertices)
    if len(faces) == 0:
        raise ChartParameterizationError("chart_empty", "chart has no triangles")
    if corner_loop_positions is None:
        corner_loop_positions = detect_rectangle_corners(
            vertices, loop, minimum_turn_deg=minimum_turn_deg
        )
    corners = np.asarray(corner_loop_positions, dtype=np.int64)
    if len(corners) != 4:
        raise ChartParameterizationError(
            "chart_corner_count", "square parameterization needs exactly four corners"
        )

    boundary_uv = _boundary_square_uv(vertices, loop, corners)
    uv = np.zeros((count, 2))
    is_boundary = np.zeros(count, dtype=bool)
    is_boundary[loop] = True
    uv[loop] = boundary_uv

    interior = np.flatnonzero(~is_boundary)
    if len(interior) > 0:
        adjacency = _mean_value_weights(vertices, faces, count)
        degree = np.asarray(adjacency.sum(axis=1)).reshape(-1)
        if np.any(degree[interior] <= 0.0):
            raise ChartParameterizationError(
                "chart_disconnected", "chart contains isolated interior vertices"
            )
        laplacian = (
            coo_matrix((degree, (np.arange(count), np.arange(count))), shape=(count, count))
            - adjacency
        ).tocsr()
        interior_system = laplacian[interior][:, interior].tocsc()
        boundary_coupling = laplacian[interior][:, np.flatnonzero(is_boundary)]
        rhs = -boundary_coupling @ uv[np.flatnonzero(is_boundary)]
        uv[interior] = splu(interior_system).solve(np.asarray(rhs))

    flipped, minimum_ratio, maximum_stretch, mean_distortion = _triangle_uv_metrics(
        vertices, faces, uv
    )
    if flipped > 0:
        raise ChartParameterizationError(
            "chart_uv_folded", f"{flipped} UV triangles are flipped or degenerate"
        )
    if maximum_stretch > maximum_stretch_limit:
        raise ChartParameterizationError(
            "chart_uv_distorted",
            f"maximum stretch {maximum_stretch:g} exceeds limit {maximum_stretch_limit:g}",
        )
    return ChartParameterization(
        uv=uv,
        boundary_loop=loop,
        corner_loop_positions=(
            int(corners[0]),
            int(corners[1]),
            int(corners[2]),
            int(corners[3]),
        ),
        flipped_triangle_count=flipped,
        minimum_uv_area_ratio=minimum_ratio,
        maximum_stretch=maximum_stretch,
        mean_area_distortion=mean_distortion,
    )


@dataclass(frozen=True, slots=True)
class ChartHalf:
    """One side of a cut chart, reindexed with its own vertex array."""

    vertices: np.ndarray = field(repr=False)
    faces: np.ndarray = field(repr=False)
    boundary_loop: np.ndarray = field(repr=False)
    corner_positions: tuple[int, int, int, int]
    parent_vertex_ids: np.ndarray = field(repr=False)


@dataclass(frozen=True, slots=True)
class ChartCut:
    """A deterministic interior cut splitting a chart into two disk halves."""

    vertices: np.ndarray = field(repr=False)
    path_vertex_ids: np.ndarray = field(repr=False)
    half_a: ChartHalf
    half_b: ChartHalf

    @property
    def path_points(self) -> np.ndarray:
        return np.asarray(self.vertices[self.path_vertex_ids], dtype=np.float64)


def _ordered_boundary_loop(faces: np.ndarray) -> np.ndarray:
    """The single closed boundary loop of a disk-like triangle subset."""

    counts: dict[tuple[int, int], int] = {}
    directed: dict[int, list[int]] = {}
    for a, b, c in faces:
        for left, right in ((int(a), int(b)), (int(b), int(c)), (int(c), int(a))):
            key = (min(left, right), max(left, right))
            counts[key] = counts.get(key, 0) + 1
    for a, b, c in faces:
        for left, right in ((int(a), int(b)), (int(b), int(c)), (int(c), int(a))):
            if counts[(min(left, right), max(left, right))] == 1:
                directed.setdefault(left, []).append(right)
    if not directed or any(len(nexts) != 1 for nexts in directed.values()):
        raise ChartParameterizationError(
            "chart_cut_boundary", "a cut side does not have one simple boundary loop"
        )
    start = min(directed)
    loop = [start]
    current = directed[start][0]
    while current != start:
        loop.append(current)
        current = directed[current][0]
        if len(loop) > len(directed) + 1:
            raise ChartParameterizationError(
                "chart_cut_boundary", "a cut side's boundary walk did not close"
            )
    return np.asarray(loop, dtype=np.int64)


def _reindexed_half(
    vertices: np.ndarray, faces: np.ndarray, corner_vertex_ids: tuple[int, int, int, int]
) -> ChartHalf:
    used = np.unique(faces)
    local = np.full(len(vertices), -1, dtype=np.int64)
    local[used] = np.arange(len(used))
    loop = _ordered_boundary_loop(local[faces])
    corner_local = [int(local[vertex]) for vertex in corner_vertex_ids]
    positions = []
    for corner in corner_local:
        found = np.flatnonzero(loop == corner)
        if len(found) != 1:
            raise ChartParameterizationError(
                "chart_cut_corner", "a cut corner is missing from the side boundary"
            )
        positions.append(int(found[0]))
    # The walk direction is arbitrary; normalize so corners appear in the
    # requested cyclic order, flipping the loop when they run backwards.
    ranks = np.argsort(positions)
    steps = {(int(ranks[(k + 1) % 4]) - int(ranks[k])) % 4 for k in range(4)}
    if steps == {3}:
        loop = loop[::-1].copy()
        positions = [len(loop) - 1 - position for position in positions]
    elif steps != {1}:
        raise ChartParameterizationError(
            "chart_cut_corner", "cut corners are not in cyclic order on the side boundary"
        )
    rolled = np.roll(loop, -positions[0])
    positions = [(position - positions[0]) % len(loop) for position in positions]
    if positions[0] != 0 or not positions[1] < positions[2] < positions[3]:
        raise ChartParameterizationError(
            "chart_cut_corner", "cut corners are not in cyclic order on the side boundary"
        )
    return ChartHalf(
        vertices=vertices[used],
        faces=local[faces],
        boundary_loop=rolled,
        corner_positions=(positions[0], positions[1], positions[2], positions[3]),
        parent_vertex_ids=used,
    )


def _split_boundary_edge(
    vertices: np.ndarray,
    faces: np.ndarray,
    uv: np.ndarray,
    loop: np.ndarray,
    chain_positions: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Insert the midpoint of the chain's boundary edge closest to u = 0.5."""

    chain_edges = [
        (int(loop[chain_positions[k]]), int(loop[chain_positions[k + 1]]))
        for k in range(len(chain_positions) - 1)
    ]
    mid_u = np.asarray([(uv[a][0] + uv[b][0]) / 2.0 for a, b in chain_edges])
    edge = chain_edges[int(np.argmin(np.abs(mid_u - 0.5)))]
    midpoint = (vertices[edge[0]] + vertices[edge[1]]) / 2.0
    mid_uv = (uv[edge[0]] + uv[edge[1]]) / 2.0
    new_id = len(vertices)
    vertices = np.vstack([vertices, midpoint[None, :]])
    uv = np.vstack([uv, mid_uv[None, :]])

    owner = -1
    replacement: list[np.ndarray] = []
    for index, (a, b, c) in enumerate(np.asarray(faces)):
        cycle = ((int(a), int(b), int(c)), (int(b), int(c), int(a)), (int(c), int(a), int(b)))
        for left, right, apex in cycle:
            if (left, right) == edge or (right, left) == edge:
                owner = index
                replacement = [
                    np.asarray([left, new_id, apex], dtype=np.int64),
                    np.asarray([new_id, right, apex], dtype=np.int64),
                ]
                break
        if owner >= 0:
            break
    if owner < 0:
        raise ChartParameterizationError(
            "chart_cut_edge", "the selected boundary edge has no incident chart triangle"
        )
    faces = np.vstack(
        [np.delete(faces, owner, axis=0), replacement[0][None, :], replacement[1][None, :]]
    )
    return vertices, faces, uv, new_id


def cut_chart_midline(
    vertices: np.ndarray,
    faces: np.ndarray,
    chart: ChartParameterization,
) -> ChartCut:
    """Split a four-cornered chart along a deterministic interior path.

    The path runs from the v=0 boundary chain to the v=1 chain, staying near
    the u = 0.5 isoline of the chart's harmonic map. Both endpoints are
    inserted boundary-edge midpoints, so straight crease boundaries that never
    subdivide still admit a cut. Fails closed unless the cut yields exactly
    two disk-like sides.
    """

    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    uv = np.asarray(chart.uv, dtype=np.float64)
    loop = np.asarray(chart.boundary_loop, dtype=np.int64)
    corners = np.asarray(chart.corner_loop_positions, dtype=np.int64)
    count = len(loop)

    def chain(start_corner: int) -> np.ndarray:
        start = int(corners[start_corner])
        end = int(corners[(start_corner + 1) % 4])
        if end <= start:
            end += count
        return np.arange(start, end + 1) % count

    vertices, faces, uv, start_id = _split_boundary_edge(vertices, faces, uv, loop, chain(0))
    vertices, faces, uv, end_id = _split_boundary_edge(vertices, faces, uv, loop, chain(2))

    boundary = set(int(vertex) for vertex in loop)
    adjacency: dict[int, list[tuple[float, int]]] = {}
    for a, b, c in faces:
        for left, right in ((int(a), int(b)), (int(b), int(c)), (int(c), int(a))):
            length = float(np.linalg.norm(vertices[left] - vertices[right]))
            penalty = 1.0 + 4.0 * (abs(uv[left][0] - 0.5) + abs(uv[right][0] - 0.5))
            weight = length * penalty
            adjacency.setdefault(left, []).append((weight, right))
            adjacency.setdefault(right, []).append((weight, left))

    distances = {start_id: 0.0}
    previous: dict[int, int] = {}
    queue: list[tuple[float, int]] = [(0.0, start_id)]
    visited: set[int] = set()
    while queue:
        distance, node = heapq.heappop(queue)
        if node in visited:
            continue
        visited.add(node)
        if node == end_id:
            break
        for weight, neighbor in sorted(adjacency.get(node, [])):
            if neighbor in boundary and neighbor != end_id:
                continue
            candidate = distance + weight
            if candidate < distances.get(neighbor, np.inf):
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))
    if end_id not in visited:
        raise ChartParameterizationError(
            "chart_cut_no_path", "no interior path exists between the cut endpoints"
        )
    path = [end_id]
    while path[-1] != start_id:
        path.append(previous[path[-1]])
    path_ids = np.asarray(path[::-1], dtype=np.int64)

    path_edges = {(min(int(a), int(b)), max(int(a), int(b))) for a, b in pairwise(path_ids)}
    edge_to_faces: dict[tuple[int, int], list[int]] = {}
    for index, (a, b, c) in enumerate(faces):
        for left, right in ((int(a), int(b)), (int(b), int(c)), (int(c), int(a))):
            edge_to_faces.setdefault((min(left, right), max(left, right)), []).append(index)
    parent = np.arange(len(faces))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = int(parent[node])
        return node

    for edge, incident in edge_to_faces.items():
        if edge in path_edges or len(incident) != 2:
            continue
        left_root, right_root = find(incident[0]), find(incident[1])
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)
    roots = np.asarray([find(index) for index in range(len(faces))])
    components = np.unique(roots)
    if len(components) != 2:
        raise ChartParameterizationError(
            "chart_cut_components",
            f"the cut produced {len(components)} sides instead of exactly two",
        )

    corner_ids = [int(loop[position]) for position in corners]
    side_faces = [faces[roots == component] for component in components]
    contains_c0 = [bool(np.any(side == corner_ids[0])) for side in side_faces]
    if contains_c0 == [True, False]:
        faces_a, faces_b = side_faces
    elif contains_c0 == [False, True]:
        faces_b, faces_a = side_faces
    else:
        raise ChartParameterizationError(
            "chart_cut_components", "could not attribute the chart corners to one side each"
        )

    half_a = _reindexed_half(vertices, faces_a, (corner_ids[0], start_id, end_id, corner_ids[3]))
    half_b = _reindexed_half(vertices, faces_b, (start_id, corner_ids[1], corner_ids[2], end_id))
    return ChartCut(
        vertices=vertices,
        path_vertex_ids=path_ids,
        half_a=half_a,
        half_b=half_b,
    )


__all__ = [
    "ChartCut",
    "ChartHalf",
    "ChartParameterization",
    "ChartParameterizationError",
    "cut_chart_midline",
    "detect_rectangle_corners",
    "harmonic_square_parameterization",
]
