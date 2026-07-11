"""Hash-bound GLB triangle selection metadata for surface patches."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .segmentation import SurfacePatch
from .tessellation import MeshArtifact, Tessellation, write_glb

Vertex = tuple[float, float, float]
CoordinateTriangle = tuple[Vertex, Vertex, Vertex]


@dataclass(frozen=True, slots=True)
class SelectionRange:
    triangle_start: int
    triangle_end_exclusive: int
    patch_id: str
    semantic_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "triangleStart": self.triangle_start,
            "triangleEndExclusive": self.triangle_end_exclusive,
            "patchId": self.patch_id,
            "semanticIds": list(self.semantic_ids),
        }


@dataclass(frozen=True, slots=True)
class SelectionMapArtifact:
    path: str
    sha256: str
    byte_size: int
    glb: MeshArtifact
    ranges: tuple[SelectionRange, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "byteSize": self.byte_size,
            "glb": {
                "path": self.glb.path,
                "format": self.glb.format,
                "byteSize": self.glb.byte_size,
                "sha256": self.glb.sha256,
                "vertexCount": self.glb.vertex_count,
                "triangleCount": self.glb.triangle_count,
                "linearTolerance": self.glb.linear_tolerance,
                "angularTolerance": self.glb.angular_tolerance,
            },
            "ranges": [item.to_dict() for item in self.ranges],
        }


def _quantized_vertex(vertex: np.ndarray, resolution: float = 1e-6) -> Vertex:
    values = [round(float(value) / resolution) * resolution for value in vertex]
    return (
        0.0 if values[0] == 0 else values[0],
        0.0 if values[1] == 0 else values[1],
        0.0 if values[2] == 0 else values[2],
    )


def _canonical_triangle(vertices: np.ndarray) -> CoordinateTriangle:
    triangle: CoordinateTriangle = (
        _quantized_vertex(vertices[0]),
        _quantized_vertex(vertices[1]),
        _quantized_vertex(vertices[2]),
    )
    rotations = (
        triangle,
        (triangle[1], triangle[2], triangle[0]),
        (triangle[2], triangle[0], triangle[1]),
    )
    return min(rotations)


def _selection_ranges(tags: list[str]) -> tuple[SelectionRange, ...]:
    if not tags:
        return ()
    ranges: list[SelectionRange] = []
    start, current = 0, tags[0]
    for index, tag in enumerate(tags[1:], start=1):
        if tag != current:
            ranges.append(SelectionRange(start, index, current, (current,)))
            start, current = index, tag
    ranges.append(SelectionRange(start, len(tags), current, (current,)))
    return tuple(ranges)


def write_patch_selection_artifacts(
    mesh: trimesh.Trimesh,
    patches: tuple[SurfacePatch, ...] | list[SurfacePatch],
    glb_path: str | Path,
    selection_map_path: str | Path,
) -> SelectionMapArtifact:
    """Canonicalize triangles together with patch tags and bind map to GLB hash."""

    if len(mesh.faces) == 0:
        raise ValueError("cannot export patch selection for an empty mesh")
    face_tags: list[str | None] = [None] * len(mesh.faces)
    for patch in patches:
        for face_id in patch.triangle_ids:
            if face_id < 0 or face_id >= len(face_tags):
                raise ValueError(f"patch {patch.id} has out-of-range triangle {face_id}")
            if face_tags[face_id] is not None:
                raise ValueError(f"triangle {face_id} belongs to multiple patches")
            face_tags[face_id] = patch.id
    missing = [index for index, tag in enumerate(face_tags) if tag is None]
    if missing:
        raise ValueError(f"selection map has {len(missing)} unassigned triangles")
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    tagged = [
        (_canonical_triangle(vertices[face]), str(face_tags[index]))
        for index, face in enumerate(faces)
    ]
    tagged.sort(key=lambda item: item[0])
    if len({triangle for triangle, _ in tagged}) != len(tagged):
        raise ValueError("duplicate coordinate triangles cannot be selection-mapped unambiguously")
    canonical_vertices = tuple(sorted({vertex for triangle, _ in tagged for vertex in triangle}))
    vertex_index = {vertex: index for index, vertex in enumerate(canonical_vertices)}
    canonical_triangles = tuple(
        (vertex_index[triangle[0]], vertex_index[triangle[1]], vertex_index[triangle[2]])
        for triangle, _ in tagged
    )
    tessellation = Tessellation(canonical_vertices, canonical_triangles, ())
    glb = write_glb(tessellation, glb_path)
    tags = [tag for _, tag in tagged]
    ranges = _selection_ranges(tags)
    patch_by_id = {patch.id: patch for patch in patches}
    document = {
        "schemaVersion": "1.0.0",
        "artifact": {
            "path": Path(glb.path).name,
            "sha256": glb.sha256,
            "byteSize": glb.byte_size,
            "triangleCount": glb.triangle_count,
        },
        "tagKind": "patchId",
        "canonicalization": "triangle coordinates and patch tags sorted together at 1e-6 mm",
        "ranges": [item.to_dict() for item in ranges],
        "patches": {
            patch_id: {
                "type": patch.kind,
                "residualsMm": patch.residuals_mm.to_dict(),
                "confidence": patch.confidence,
            }
            for patch_id, patch in sorted(patch_by_id.items())
        },
    }
    payload = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    destination = Path(selection_map_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return SelectionMapArtifact(
        path=str(destination),
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
        glb=glb,
        ranges=ranges,
    )


__all__ = [
    "SelectionMapArtifact",
    "SelectionRange",
    "write_patch_selection_artifacts",
]
