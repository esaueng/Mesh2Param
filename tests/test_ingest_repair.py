from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import trimesh
from mesh2param.ingest import (
    MeshIngestionError,
    MeshLimits,
    ingest_bytes,
    ingest_mesh,
)
from mesh2param.repair import (
    DEFAULT_REPAIR_SETTINGS,
    DETERMINISTIC_OPERATION_TIMESTAMP,
    RepairSettings,
    geometry_fingerprint,
    repair_mesh,
)


def _payload(mesh: trimesh.Trimesh, file_type: str, **kwargs: str) -> bytes:
    exported = mesh.export(file_type=file_type, **kwargs)
    if isinstance(exported, str):
        return exported.encode("utf-8")
    if isinstance(exported, bytes):
        return exported
    raise TypeError(f"unexpected trimesh export type: {type(exported).__name__}")


@pytest.mark.parametrize(
    ("filename", "file_type", "kwargs", "encoding"),
    [
        ("box.stl", "stl", {}, "binary-little-endian"),
        ("box.stl", "stl_ascii", {}, "ascii-utf8"),
        ("box.obj", "obj", {}, "ascii-utf8"),
        ("box.ply", "ply", {"encoding": "ascii"}, "ascii"),
        (
            "box.ply",
            "ply",
            {"encoding": "binary_little_endian"},
            "binary-little-endian",
        ),
    ],
)
def test_supported_formats_preserve_source_and_report_diagnostics(
    filename: str,
    file_type: str,
    kwargs: dict[str, str],
    encoding: str,
) -> None:
    source = trimesh.creation.box(extents=(10.0, 20.0, 30.0))
    payload = _payload(source, file_type, **kwargs)

    result = ingest_bytes(payload, filename)

    assert result.original_bytes is payload
    assert result.metadata.byte_size == len(payload)
    assert result.metadata.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.metadata.original_bytes_preserved
    assert result.metadata.encoding == encoding
    assert result.source_id == f"source:{result.metadata.sha256}"
    assert result.diagnostics.triangle_count == 12
    assert result.diagnostics.welded_vertex_count == 8
    assert result.diagnostics.connected_component_count == 1
    assert result.diagnostics.bounding_dimensions == pytest.approx((10.0, 20.0, 30.0))
    assert result.diagnostics.surface_area == pytest.approx(2200.0)
    assert result.diagnostics.closed_volume == pytest.approx(6000.0)
    assert result.diagnostics.watertight
    assert result.diagnostics.winding_consistent
    assert result.diagnostics.open_boundary_edge_count == 0
    assert result.diagnostics.non_manifold_edge_count == 0
    assert result.diagnostics.self_intersection_status == "unverified"
    assert "self_intersection_unverified" in {
        warning.code for warning in result.diagnostics.warnings
    }
    if file_type.startswith("stl"):
        assert result.diagnostics.raw_vertex_count == 36
        assert result.diagnostics.duplicate_vertex_count == 28
    else:
        assert result.diagnostics.raw_vertex_count == 8


def test_path_ingestion_rejects_non_files_and_symlinks(tmp_path: Path) -> None:
    payload = _payload(trimesh.creation.icosphere(subdivisions=1), "stl")
    mesh_path = tmp_path / "mesh.stl"
    mesh_path.write_bytes(payload)
    link_path = tmp_path / "link.stl"
    link_path.symlink_to(mesh_path)

    assert ingest_mesh(mesh_path).metadata.sha256 == hashlib.sha256(payload).hexdigest()
    with pytest.raises(MeshIngestionError, match="regular file") as directory_error:
        ingest_mesh(tmp_path)
    assert directory_error.value.code == "invalid_path"
    with pytest.raises(MeshIngestionError, match="symbolic-link") as symlink_error:
        ingest_mesh(link_path)
    assert symlink_error.value.code == "invalid_path"


@pytest.mark.parametrize(
    ("payload", "filename", "code"),
    [
        (b"", "empty.stl", "empty_file"),
        (b"PK\x03\x04not-a-mesh", "archive.stl", "forbidden_content"),
        (b"MZnot-a-mesh", "program.obj", "forbidden_content"),
        (b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", "wrong.stl", "content_mismatch"),
        (b"solid x\nendsolid x\n", "wrong.obj", "content_mismatch"),
    ],
)
def test_empty_forbidden_and_mismatched_content_is_rejected(
    payload: bytes, filename: str, code: str
) -> None:
    with pytest.raises(MeshIngestionError) as error:
        ingest_bytes(payload, filename)
    assert error.value.code == code


def test_limits_reject_excessive_bytes_counts_and_coordinates() -> None:
    triangle = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
    with pytest.raises(MeshIngestionError) as byte_error:
        ingest_bytes(triangle, "triangle.obj", limits=MeshLimits(max_file_bytes=8))
    assert byte_error.value.code == "excessive_bytes"

    two_faces = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\nf 1 3 2\n"
    with pytest.raises(MeshIngestionError) as triangle_error:
        ingest_bytes(two_faces, "two.obj", limits=MeshLimits(max_triangles=1))
    assert triangle_error.value.code == "excessive_triangles"

    four_vertices = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nv 2 2 2\nf 1 2 3\n"
    with pytest.raises(MeshIngestionError) as vertex_error:
        ingest_bytes(four_vertices, "four.obj", limits=MeshLimits(max_vertices=3))
    assert vertex_error.value.code == "excessive_vertices"

    extreme = b"v 0 0 0\nv 10 0 0\nv 0 1 0\nf 1 2 3\n"
    with pytest.raises(MeshIngestionError) as coordinate_error:
        ingest_bytes(extreme, "extreme.obj", limits=MeshLimits(max_abs_coordinate=5.0))
    assert coordinate_error.value.code == "extreme_coordinates"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (
            b"v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n",
            "non_triangle_face",
        ),
        (b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 9\n", "malformed_indices"),
        (b"v 0 0 0\nv nan 0 0\nv 0 1 0\nf 1 2 3\n", "non_finite_coordinate"),
    ],
)
def test_obj_preflight_rejects_polygons_bad_indices_and_non_finite_values(
    payload: bytes, code: str
) -> None:
    with pytest.raises(MeshIngestionError) as error:
        ingest_bytes(payload, "bad.obj")
    assert error.value.code == code


def test_ascii_and_binary_ply_non_triangle_faces_are_rejected() -> None:
    header = (
        b"ply\nformat ascii 1.0\n"
        b"element vertex 4\nproperty float x\nproperty float y\nproperty float z\n"
        b"element face 1\nproperty list uchar int vertex_indices\nend_header\n"
    )
    ascii_quad = header + b"0 0 0\n1 0 0\n1 1 0\n0 1 0\n4 0 1 2 3\n"
    with pytest.raises(MeshIngestionError) as ascii_error:
        ingest_bytes(ascii_quad, "quad.ply")
    assert ascii_error.value.code == "non_triangle_face"

    binary_header = header.replace(b"format ascii", b"format binary_little_endian")
    vertices = struct.pack("<12f", 0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0)
    face = struct.pack("<B4i", 4, 0, 1, 2, 3)
    with pytest.raises(MeshIngestionError) as binary_error:
        ingest_bytes(binary_header + vertices + face, "quad.ply")
    assert binary_error.value.code == "non_triangle_face"


def _damaged_mesh() -> trimesh.Trimesh:
    return trimesh.Trimesh(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],  # exact duplicate used by the first face
                [9.0, 9.0, 9.0],  # unreferenced
            ]
        ),
        faces=np.asarray(
            [
                [4, 1, 2],
                [0, 2, 3],
                [0, 2, 3],  # duplicate face
                [0, 0, 1],  # degenerate face
            ]
        ),
        process=False,
    )


def test_repair_is_non_destructive_explicit_and_deterministic() -> None:
    source = _damaged_mesh()
    source_vertices = np.asarray(source.vertices).copy()
    source_faces = np.asarray(source.faces).copy()
    source_fingerprint = geometry_fingerprint(source)

    first = repair_mesh(source)
    second = repair_mesh(source)

    np.testing.assert_array_equal(source.vertices, source_vertices)
    np.testing.assert_array_equal(source.faces, source_faces)
    assert geometry_fingerprint(source) == source_fingerprint
    assert first.result_id == second.result_id
    assert [record.to_dict() for record in first.operations] == [
        record.to_dict() for record in second.operations
    ]
    assert first.result_metrics.vertex_count == 4
    assert first.result_metrics.triangle_count == 2
    assert first.result_metrics.degenerate_triangle_count == 0
    assert first.result_metrics.duplicate_face_count == 0

    expected_order = [
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
    assert [operation.operation for operation in first.operations] == expected_order
    assert [operation.order for operation in first.operations] == list(range(1, 10))
    assert all(operation.reversible for operation in first.operations)
    assert all(
        operation.timestamp == DETERMINISTIC_OPERATION_TIMESTAMP for operation in first.operations
    )
    assert first.operations[0].parameters == {"tolerance": 1e-8}
    assert first.operations[0].source_version_id == first.source_id
    for previous, following in zip(first.operations[:-1], first.operations[1:], strict=True):
        assert previous.result_version_id == following.source_version_id
        assert previous.after == following.before
    assert first.operations[-1].result_version_id == first.result_id


def test_disabled_repair_operations_are_records_and_do_not_modify_geometry() -> None:
    source = _damaged_mesh()
    settings = replace(
        DEFAULT_REPAIR_SETTINGS,
        merge_duplicate_vertices=False,
        remove_degenerate_faces=False,
        remove_duplicate_faces=False,
        remove_unreferenced_vertices=False,
        orient_winding=False,
        repair_normals=False,
        keep_largest_component=False,
        drop_tiny_components=False,
        fill_small_holes=False,
    )

    result = repair_mesh(source, settings)

    assert len(result.operations) == 9
    assert not any(operation.enabled for operation in result.operations)
    assert not any(operation.changed for operation in result.operations)
    assert result.result_id == result.source_id
    assert geometry_fingerprint(result.mesh) == geometry_fingerprint(source)
    assert not hasattr(settings, "smoothing")
    assert not hasattr(settings, "decimation")


@pytest.mark.parametrize(
    ("field_name", "operation_name"),
    [
        ("merge_duplicate_vertices", "merge_duplicate_vertices"),
        ("remove_degenerate_faces", "remove_degenerate_faces"),
        ("remove_duplicate_faces", "remove_duplicate_faces"),
        ("remove_unreferenced_vertices", "remove_unreferenced_vertices"),
        ("orient_winding", "orient_winding"),
        ("repair_normals", "repair_normals"),
        ("keep_largest_component", "keep_largest_component"),
        ("drop_tiny_components", "drop_tiny_components"),
        ("fill_small_holes", "fill_small_holes"),
    ],
)
def test_each_repair_operation_can_be_enabled_independently(
    field_name: str,
    operation_name: str,
) -> None:
    disabled = replace(
        DEFAULT_REPAIR_SETTINGS,
        merge_duplicate_vertices=False,
        remove_degenerate_faces=False,
        remove_duplicate_faces=False,
        remove_unreferenced_vertices=False,
        orient_winding=False,
        repair_normals=False,
        keep_largest_component=False,
        drop_tiny_components=False,
        fill_small_holes=False,
    )
    settings = replace(disabled, **{field_name: True})

    result = repair_mesh(_damaged_mesh(), settings)

    assert [record.operation for record in result.operations if record.enabled] == [operation_name]


def test_component_filters_are_opt_in_and_record_dropped_bodies() -> None:
    large = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    tiny = trimesh.creation.box(extents=(0.1, 0.1, 0.1))
    tiny.apply_translation((10.0, 0.0, 0.0))
    source = trimesh.util.concatenate((large, tiny))

    untouched = repair_mesh(source)
    kept = repair_mesh(source, replace(DEFAULT_REPAIR_SETTINGS, keep_largest_component=True))
    dropped = repair_mesh(
        source,
        replace(
            DEFAULT_REPAIR_SETTINGS,
            drop_tiny_components=True,
            tiny_component_area_ratio=0.01,
        ),
    )

    assert untouched.result_metrics.connected_component_count == 2
    assert kept.result_metrics.connected_component_count == 1
    assert kept.result_metrics.closed_volume == pytest.approx(8.0)
    assert any("Dropped 1" in warning for warning in kept.warnings)
    assert dropped.result_metrics.connected_component_count == 1
    assert dropped.result_metrics.closed_volume == pytest.approx(8.0)


def test_small_planar_hole_fill_is_bounded_and_explicit() -> None:
    box = trimesh.creation.box()
    keep = np.asarray(box.face_normals)[:, 2] < 0.9
    open_box = trimesh.Trimesh(
        vertices=np.asarray(box.vertices).copy(),
        faces=np.asarray(box.faces)[keep].copy(),
        process=False,
    )
    original_faces = np.asarray(open_box.faces).copy()

    disabled = repair_mesh(open_box)
    enabled = repair_mesh(
        open_box,
        RepairSettings(fill_small_holes=True, max_hole_edges=4),
    )

    assert not disabled.result_metrics.watertight
    assert enabled.result_metrics.watertight
    assert enabled.result_metrics.triangle_count == len(original_faces) + 2
    fill_record = enabled.operations[-1]
    assert fill_record.operation == "fill_small_holes"
    assert fill_record.enabled and fill_record.changed
    assert fill_record.parameters["max_boundary_edges"] == 4
    assert any("Filled 1" in warning for warning in fill_record.warnings)
    np.testing.assert_array_equal(open_box.faces, original_faces)


def test_repair_timestamp_requires_timezone() -> None:
    with pytest.raises(ValueError, match="timezone"):
        repair_mesh(_damaged_mesh(), operation_timestamp="2026-07-11T12:00:00")
    result = repair_mesh(_damaged_mesh(), operation_timestamp="2026-07-11T12:00:00-04:00")
    assert {operation.timestamp for operation in result.operations} == {"2026-07-11T12:00:00-04:00"}


def _assert_camel_case_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            assert isinstance(key, str)
            assert "_" not in key, f"serialized key is not camelCase: {key}"
            _assert_camel_case_keys(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            _assert_camel_case_keys(nested)


def test_public_serialization_is_recursively_camel_case_and_json_safe() -> None:
    payload = _payload(trimesh.creation.box(), "stl")
    ingested = ingest_bytes(payload, "box.stl")
    repaired = repair_mesh(ingested)

    serialized = {
        "limits": MeshLimits().to_dict(),
        "ingested": ingested.to_dict(),
        "repair": repaired.to_dict(),
    }
    _assert_camel_case_keys(serialized)
    roundtrip = json.loads(json.dumps(serialized, sort_keys=True, allow_nan=False))

    assert roundtrip["ingested"]["sourceId"] == ingested.source_id
    assert roundtrip["ingested"]["metadata"]["byteSize"] == len(payload)
    assert roundtrip["repair"]["settings"]["mergeDuplicateVertices"] is True
    assert roundtrip["repair"]["operations"][0]["sourceVersionId"] == repaired.source_id
    assert "rawVertexCount" in roundtrip["repair"]["diagnostics"]
