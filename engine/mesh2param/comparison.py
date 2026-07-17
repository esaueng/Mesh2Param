"""Deterministic source/result comparison and residual heatmap artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cadquery as cq
import numpy as np
import trimesh

from .tessellation import Tessellation, tessellate_shape
from .validation import import_step_shape, validate_shape


@dataclass(frozen=True, slots=True)
class ComparisonSettings:
    sample_count_each_direction: int = 1000
    deterministic_seed: int = 0x4D325006
    tolerance_mm: float = 0.1
    linear_tessellation_mm: float = 0.025
    angular_tessellation_rad: float = 0.1
    query_chunk_size: int = 80

    def validate(self) -> None:
        if self.sample_count_each_direction < 1:
            raise ValueError("comparison sample count must be positive")
        if self.tolerance_mm <= 0:
            raise ValueError("comparison tolerance must be positive")
        if self.query_chunk_size < 1:
            raise ValueError("query chunk size must be positive")


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    method: str
    sample_count_each_direction: int
    rms_distance_mm: float
    median_distance_mm: float
    p95_distance_mm: float
    p99_distance_mm: float
    maximum_distance_mm: float
    mean_normal_agreement: float
    mean_normal_angle_deg: float
    p95_normal_angle_deg: float
    source_bbox_mm: tuple[float, float, float, float, float, float]
    result_bbox_mm: tuple[float, float, float, float, float, float]
    bbox_dimension_delta_mm: tuple[float, float, float]
    source_area_mm2: float
    result_area_mm2: float
    absolute_area_delta_mm2: float
    relative_area_delta: float
    source_volume_mm3: float | None
    result_volume_mm3: float | None
    absolute_volume_delta_mm3: float | None
    relative_volume_delta: float | None
    tolerance_mm: float
    tolerance_surface_coverage: float
    source_unmatched_area_estimate_mm2: float
    result_excess_area_estimate_mm2: float
    warnings: tuple[str, ...]
    source_vertex_residuals_mm: tuple[float, ...]

    def to_dict(self, *, include_vertex_residuals: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "method": self.method,
            "sampleCountEachDirection": self.sample_count_each_direction,
            "distanceMm": {
                "rms": self.rms_distance_mm,
                "median": self.median_distance_mm,
                "p95": self.p95_distance_mm,
                "p99": self.p99_distance_mm,
                "max": self.maximum_distance_mm,
            },
            "normals": {
                "meanAgreement": self.mean_normal_agreement,
                "meanAngleDeg": self.mean_normal_angle_deg,
                "p95AngleDeg": self.p95_normal_angle_deg,
            },
            "boundingBoxMm": {
                "source": list(self.source_bbox_mm),
                "result": list(self.result_bbox_mm),
                "dimensionDelta": list(self.bbox_dimension_delta_mm),
            },
            "areaMm2": {
                "source": self.source_area_mm2,
                "result": self.result_area_mm2,
                "absoluteDelta": self.absolute_area_delta_mm2,
                "relativeDelta": self.relative_area_delta,
            },
            "volumeMm3": {
                "source": self.source_volume_mm3,
                "result": self.result_volume_mm3,
                "absoluteDelta": self.absolute_volume_delta_mm3,
                "relativeDelta": self.relative_volume_delta,
            },
            "toleranceMm": self.tolerance_mm,
            "toleranceSurfaceCoverage": self.tolerance_surface_coverage,
            "sourceUnmatchedAreaEstimateMm2": self.source_unmatched_area_estimate_mm2,
            "resultExcessAreaEstimateMm2": self.result_excess_area_estimate_mm2,
            "warnings": list(self.warnings),
        }
        if include_vertex_residuals:
            result["sourceVertexResidualsMm"] = list(self.source_vertex_residuals_mm)
        return result


@dataclass(frozen=True, slots=True)
class ResidualHeatmapArtifact:
    path: str
    byte_size: int
    sha256: str
    vertex_count: int
    triangle_count: int
    tolerance_mm: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "byteSize": self.byte_size,
            "sha256": self.sha256,
            "vertexCount": self.vertex_count,
            "triangleCount": self.triangle_count,
            "toleranceMm": self.tolerance_mm,
        }


def _require_mesh(mesh: trimesh.Trimesh, label: str) -> None:
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError(f"{label} mesh is empty")
    if not np.all(np.isfinite(mesh.vertices)):
        raise ValueError(f"{label} mesh contains non-finite vertices")
    if np.any(np.asarray(mesh.faces) < 0) or np.any(np.asarray(mesh.faces) >= len(mesh.vertices)):
        raise ValueError(f"{label} mesh contains out-of-range indices")


def mesh_from_shape(
    shape: cq.Shape | cq.Workplane,
    *,
    linear_tolerance: float = 0.025,
    angular_tolerance: float = 0.1,
    transform: np.ndarray | None = None,
) -> trimesh.Trimesh:
    validation = validate_shape(shape, require_tessellation=False)
    if not validation.valid:
        raise ValueError("refusing comparison for invalid B-Rep: " + "; ".join(validation.errors))
    tessellation = tessellate_shape(
        shape,
        linear_tolerance=linear_tolerance,
        angular_tolerance=angular_tolerance,
    )
    result = trimesh.Trimesh(
        vertices=np.asarray(tessellation.vertices, dtype=np.float64),
        faces=np.asarray(tessellation.triangles, dtype=np.int64),
        process=False,
        validate=False,
    )
    if transform is not None:
        matrix = np.asarray(transform, dtype=np.float64)
        if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
            raise ValueError("comparison transform must be a finite 4x4 matrix")
        result.apply_transform(matrix)
    _require_mesh(result, "result")
    return result


def _closest_surface(
    mesh: trimesh.Trimesh,
    points: np.ndarray,
    chunk_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    closest_point_naive = cast(
        Callable[
            [trimesh.Trimesh, np.ndarray],
            tuple[np.ndarray, np.ndarray, np.ndarray],
        ],
        trimesh.proximity.closest_point_naive,
    )
    distances: list[np.ndarray] = []
    triangle_ids: list[np.ndarray] = []
    for start in range(0, len(points), chunk_size):
        _, distance, triangle_id = closest_point_naive(mesh, points[start : start + chunk_size])
        distances.append(np.asarray(distance, dtype=np.float64))
        triangle_ids.append(np.asarray(triangle_id, dtype=np.int64))
    return np.concatenate(distances), np.concatenate(triangle_ids)


def _bbox(mesh: trimesh.Trimesh) -> tuple[float, float, float, float, float, float]:
    bounds = np.asarray(mesh.bounds, dtype=np.float64)
    return (
        float(bounds[0, 0]),
        float(bounds[0, 1]),
        float(bounds[0, 2]),
        float(bounds[1, 0]),
        float(bounds[1, 1]),
        float(bounds[1, 2]),
    )


def compare_meshes(
    source: trimesh.Trimesh,
    result: trimesh.Trimesh,
    settings: ComparisonSettings | None = None,
) -> ComparisonReport:
    settings = settings or ComparisonSettings()
    settings.validate()
    _require_mesh(source, "source")
    _require_mesh(result, "result")
    source_points, source_face_ids = trimesh.sample.sample_surface(
        source,
        settings.sample_count_each_direction,
        seed=settings.deterministic_seed,
    )
    result_points, result_face_ids = trimesh.sample.sample_surface(
        result,
        settings.sample_count_each_direction,
        seed=settings.deterministic_seed + 1,
    )
    source_to_result, result_nearest_faces = _closest_surface(
        result, source_points, settings.query_chunk_size
    )
    result_to_source, source_nearest_faces = _closest_surface(
        source, result_points, settings.query_chunk_size
    )
    combined = np.concatenate((source_to_result, result_to_source))
    source_dots = np.einsum(
        "ij,ij->i",
        np.asarray(source.face_normals)[source_face_ids],
        np.asarray(result.face_normals)[result_nearest_faces],
    )
    result_dots = np.einsum(
        "ij,ij->i",
        np.asarray(result.face_normals)[result_face_ids],
        np.asarray(source.face_normals)[source_nearest_faces],
    )
    normal_dots = np.clip(np.concatenate((source_dots, result_dots)), -1.0, 1.0)
    normal_angles = np.degrees(np.arccos(normal_dots))
    source_bbox, result_bbox = _bbox(source), _bbox(result)
    source_dimensions = np.asarray(source_bbox[3:]) - np.asarray(source_bbox[:3])
    result_dimensions = np.asarray(result_bbox[3:]) - np.asarray(result_bbox[:3])
    source_area, result_area = float(source.area), float(result.area)
    area_delta = abs(source_area - result_area)
    warnings: list[str] = [
        "distance extrema and unmatched/excess areas are deterministic sampled estimates, "
        "not exact Hausdorff/area proofs"
    ]
    source_volume: float | None = None
    result_volume: float | None = None
    volume_delta: float | None = None
    relative_volume: float | None = None
    if source.is_watertight and result.is_watertight:
        source_volume, result_volume = abs(float(source.volume)), abs(float(result.volume))
        volume_delta = abs(source_volume - result_volume)
        relative_volume = volume_delta / source_volume if source_volume > 0 else math.inf
    else:
        warnings.append(
            "volume comparison unavailable because source or result mesh is not watertight"
        )
    source_unmatched_fraction = float(np.mean(source_to_result > settings.tolerance_mm))
    result_excess_fraction = float(np.mean(result_to_source > settings.tolerance_mm))
    vertex_residuals, _ = _closest_surface(
        result, np.asarray(source.vertices, dtype=np.float64), settings.query_chunk_size
    )
    return ComparisonReport(
        method="bidirectional seeded surface sampling with exact point-to-triangle queries",
        sample_count_each_direction=settings.sample_count_each_direction,
        rms_distance_mm=float(np.sqrt(np.mean(combined * combined))),
        median_distance_mm=float(np.median(combined)),
        p95_distance_mm=float(np.quantile(combined, 0.95)),
        p99_distance_mm=float(np.quantile(combined, 0.99)),
        maximum_distance_mm=float(np.max(combined)),
        mean_normal_agreement=float(np.mean(np.clip(normal_dots, 0.0, 1.0))),
        mean_normal_angle_deg=float(np.mean(normal_angles)),
        p95_normal_angle_deg=float(np.quantile(normal_angles, 0.95)),
        source_bbox_mm=source_bbox,
        result_bbox_mm=result_bbox,
        bbox_dimension_delta_mm=(
            float(result_dimensions[0] - source_dimensions[0]),
            float(result_dimensions[1] - source_dimensions[1]),
            float(result_dimensions[2] - source_dimensions[2]),
        ),
        source_area_mm2=source_area,
        result_area_mm2=result_area,
        absolute_area_delta_mm2=area_delta,
        relative_area_delta=area_delta / source_area,
        source_volume_mm3=source_volume,
        result_volume_mm3=result_volume,
        absolute_volume_delta_mm3=volume_delta,
        relative_volume_delta=relative_volume,
        tolerance_mm=settings.tolerance_mm,
        tolerance_surface_coverage=float(np.mean(combined <= settings.tolerance_mm)),
        source_unmatched_area_estimate_mm2=source_area * source_unmatched_fraction,
        result_excess_area_estimate_mm2=result_area * result_excess_fraction,
        warnings=tuple(warnings),
        source_vertex_residuals_mm=tuple(float(value) for value in vertex_residuals),
    )


def compare_mesh_to_shape(
    source: trimesh.Trimesh,
    shape: cq.Shape | cq.Workplane,
    *,
    transform: np.ndarray | None = None,
    settings: ComparisonSettings | None = None,
) -> ComparisonReport:
    settings = settings or ComparisonSettings()
    result = mesh_from_shape(
        shape,
        linear_tolerance=settings.linear_tessellation_mm,
        angular_tolerance=settings.angular_tessellation_rad,
        transform=transform,
    )
    return compare_meshes(source, result, settings)


def compare_mesh_to_step(
    source: trimesh.Trimesh,
    step_path: str | Path,
    *,
    units: str = "mm",
    settings: ComparisonSettings | None = None,
) -> ComparisonReport:
    return compare_mesh_to_shape(source, import_step_shape(step_path, units), settings=settings)


def _pad4(payload: bytes, fill: bytes) -> bytes:
    return payload + fill * ((-len(payload)) % 4)


def write_residual_heatmap_glb(
    mesh: trimesh.Trimesh,
    residuals_mm: tuple[float, ...] | np.ndarray,
    path: str | Path,
    *,
    tolerance_mm: float,
) -> ResidualHeatmapArtifact:
    """Write a minimal deterministic GLB with blue-to-red per-vertex residual colors."""

    _require_mesh(mesh, "heatmap")
    if tolerance_mm <= 0:
        raise ValueError("heatmap tolerance must be positive")
    residuals = np.asarray(residuals_mm, dtype=np.float64)
    if residuals.shape != (len(mesh.vertices),) or not np.all(np.isfinite(residuals)):
        raise ValueError("heatmap residuals must be one finite value per mesh vertex")
    vertices = np.asarray(mesh.vertices, dtype="<f4")
    normals = np.asarray(mesh.vertex_normals, dtype="<f4")
    indices = np.asarray(mesh.faces, dtype="<u4").reshape(-1)
    fraction = np.clip(residuals / tolerance_mm, 0.0, 1.0)
    colors = np.column_stack(
        (
            np.rint(255 * fraction),
            np.full(len(fraction), 32),
            np.rint(255 * (1.0 - fraction)),
            np.full(len(fraction), 255),
        )
    ).astype(np.uint8)
    chunks = [vertices.tobytes(), normals.tobytes(), colors.tobytes(), indices.tobytes()]
    offsets: list[int] = []
    binary = bytearray()
    for chunk in chunks:
        offsets.append(len(binary))
        binary.extend(chunk)
        binary.extend(b"\0" * ((-len(binary)) % 4))
    vertex_min = [float(value) for value in np.min(vertices, axis=0)]
    vertex_max = [float(value) for value in np.max(vertices, axis=0)]
    gltf = {
        "asset": {"generator": "Mesh2Param residual heatmap", "version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "COLOR_0": 2},
                        "indices": 3,
                        "material": 0,
                    }
                ]
            }
        ],
        "materials": [
            {
                "doubleSided": True,
                "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.8},
            }
        ],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": offsets[0], "byteLength": len(chunks[0]), "target": 34962},
            {"buffer": 0, "byteOffset": offsets[1], "byteLength": len(chunks[1]), "target": 34962},
            {"buffer": 0, "byteOffset": offsets[2], "byteLength": len(chunks[2]), "target": 34962},
            {"buffer": 0, "byteOffset": offsets[3], "byteLength": len(chunks[3]), "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(vertices),
                "type": "VEC3",
                "min": vertex_min,
                "max": vertex_max,
            },
            {"bufferView": 1, "componentType": 5126, "count": len(normals), "type": "VEC3"},
            {
                "bufferView": 2,
                "componentType": 5121,
                "count": len(colors),
                "type": "VEC4",
                "normalized": True,
            },
            {
                "bufferView": 3,
                "componentType": 5125,
                "count": len(indices),
                "type": "SCALAR",
                "min": [int(np.min(indices))],
                "max": [int(np.max(indices))],
            },
        ],
        "extras": {"residualToleranceMm": tolerance_mm, "colorScale": "blue-low red-high"},
    }
    json_chunk = _pad4(json.dumps(gltf, sort_keys=True, separators=(",", ":")).encode(), b" ")
    binary_chunk = _pad4(bytes(binary), b"\0")
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
    payload = (
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<I4s", len(json_chunk), b"JSON")
        + json_chunk
        + struct.pack("<I4s", len(binary_chunk), b"BIN\0")
        + binary_chunk
    )
    destination = Path(path)
    if destination.suffix.lower() != ".glb":
        raise ValueError("residual heatmap output must use .glb")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return ResidualHeatmapArtifact(
        path=str(destination),
        byte_size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        vertex_count=len(vertices),
        triangle_count=len(mesh.faces),
        tolerance_mm=tolerance_mm,
    )


def tessellation_to_mesh(mesh: Tessellation) -> trimesh.Trimesh:
    return trimesh.Trimesh(
        vertices=np.asarray(mesh.vertices, dtype=np.float64),
        faces=np.asarray(mesh.triangles, dtype=np.int64),
        process=False,
        validate=False,
    )


__all__ = [
    "ComparisonReport",
    "ComparisonSettings",
    "ResidualHeatmapArtifact",
    "compare_mesh_to_shape",
    "compare_mesh_to_step",
    "compare_meshes",
    "mesh_from_shape",
    "tessellation_to_mesh",
    "write_residual_heatmap_glb",
]
