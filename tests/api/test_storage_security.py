from __future__ import annotations

import hashlib
import io
import os
import stat
import struct
from pathlib import Path

import pytest
from mesh2param_api.security import (
    SecurityPolicyError,
    UploadLimits,
    UploadValidationError,
    api_security_headers,
    attachment_content_disposition,
    is_host_allowed,
    is_origin_allowed,
    normalize_host,
    normalize_origin,
    parse_allowed_hosts,
    parse_allowed_origins,
    preflight_mesh_upload,
    require_allowed_host,
    require_allowed_origin,
    safe_header_value,
)
from mesh2param_api.storage import (
    ByteLimitExceeded,
    LocalCAS,
    StorageIntegrityError,
    UnsafeNameError,
    UnsafeStoragePathError,
    collect_limited,
    validate_artifact_name,
    validate_display_filename,
)

ASCII_STL = b"""solid triangle
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
endsolid triangle
"""

OBJ_QUAD = b"""# bounded quad
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
f 1 2 3 4
"""

ASCII_PLY = b"""ply
format ascii 1.0
element vertex 3
property float x
property float y
property float z
element face 1
property list uchar int vertex_indices
end_header
0 0 0
1 0 0
0 1 0
3 0 1 2
"""


def _binary_stl() -> bytes:
    header = b"Mesh2Param binary STL".ljust(80, b"\0")
    triangle = struct.pack(
        "<12fH",
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0,
    )
    return header + struct.pack("<I", 1) + triangle


def _binary_ply() -> bytes:
    header = b"""ply
format binary_little_endian 1.0
element vertex 3
property float x
property float y
property float z
element face 1
property list uchar int vertex_indices
end_header
"""
    vertices = b"".join(
        struct.pack("<fff", *vertex)
        for vertex in ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    )
    return header + vertices + struct.pack("<Biii", 3, 0, 1, 2)


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _assert_upload_error(
    path: Path, display_filename: str, expected_code: str, *, limits: UploadLimits | None = None
) -> None:
    with pytest.raises(UploadValidationError) as captured:
        preflight_mesh_upload(path, display_filename, limits=limits)
    assert captured.value.code == expected_code


def test_cas_atomically_publishes_deduplicates_and_serializes_camel_case(
    tmp_path: Path,
) -> None:
    cas = LocalCAS(tmp_path / "cas", default_max_bytes=1024)

    first = cas.put_stream(io.BytesIO(b"immutable mesh"))
    second = cas.put_bytes(b"immutable mesh")

    assert first.sha256 == second.sha256
    assert first.byte_size == 14
    assert first.path == cas.root / "blobs" / "sha256" / first.sha256[:2] / first.sha256[2:]
    assert first.path.read_bytes() == b"immutable mesh"
    assert stat.S_IMODE(first.path.stat().st_mode) == 0o444
    assert first.deduplicated is False
    assert second.deduplicated is True
    assert second.to_dict()["byteSize"] == 14
    assert cas.read_bytes(first.sha256) == b"immutable mesh"
    assert cas.contains(first.sha256)
    assert cas.delete_blob(first.sha256)
    assert not cas.contains(first.sha256)
    assert not cas.delete_blob(first.sha256)
    assert list((cas.root / ".tmp").iterdir()) == []


def test_cas_enforces_caps_and_never_publishes_partial_content(tmp_path: Path) -> None:
    cas = LocalCAS(tmp_path / "cas", default_max_bytes=4)

    with pytest.raises(ByteLimitExceeded) as captured:
        cas.put_stream((b"abc", b"def"))

    assert captured.value.to_dict() == {
        "code": "byte_limit_exceeded",
        "limitBytes": 4,
        "observedBytes": 6,
    }
    assert list((cas.root / ".tmp").iterdir()) == []
    assert list((cas.root / "blobs" / "sha256").iterdir()) == []


def test_cas_rejects_source_and_destination_symlinks(tmp_path: Path) -> None:
    cas = LocalCAS(tmp_path / "cas")
    source = _write(tmp_path / "source.obj", OBJ_QUAD)
    source_link = tmp_path / "source-link.obj"
    source_link.symlink_to(source)
    with pytest.raises(UnsafeStoragePathError):
        cas.put_path(source_link)

    content = b"attacker-resistant"
    digest = hashlib.sha256(content).hexdigest()
    destination = cas.path_for(digest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(source)
    with pytest.raises(StorageIntegrityError):
        cas.put_bytes(content)


def test_cas_rejects_symlinked_storage_components(tmp_path: Path) -> None:
    root = tmp_path / "cas"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "blobs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeStoragePathError):
        LocalCAS(root)


def test_names_and_chunk_accumulation_are_path_safe_and_bounded() -> None:
    assert validate_artifact_name("analysis-proxy.glb") == "analysis-proxy.glb"
    assert validate_display_filename("br\N{LATIN SMALL LETTER A WITH DIAERESIS}cket.STL") == (
        "br\N{LATIN SMALL LETTER A WITH DIAERESIS}cket.STL"
    )
    assert collect_limited((b"ab", b"cd"), max_bytes=4) == b"abcd"

    for unsafe in ("../model.step", "nested/model.step", "con.step", ".hidden.step"):
        with pytest.raises(UnsafeNameError):
            validate_display_filename(unsafe)
    with pytest.raises(UnsafeNameError):
        validate_artifact_name("../model.step")
    with pytest.raises(ByteLimitExceeded):
        collect_limited((b"abc", b"de"), max_bytes=4)


@pytest.mark.parametrize(
    (
        "filename",
        "content",
        "expected_format",
        "expected_encoding",
        "vertices",
        "faces",
        "triangles",
    ),
    [
        ("part.stl", ASCII_STL, "stl", "ascii", 3, 1, 1),
        ("part.STL", _binary_stl(), "stl", "binary", 3, 1, 1),
        ("part.obj", OBJ_QUAD, "obj", "ascii", 4, 1, 2),
        ("part.ply", ASCII_PLY, "ply", "ascii", 3, 1, 1),
        ("part.ply", _binary_ply(), "ply", "binary_little_endian", 3, 1, 1),
    ],
)
def test_preflight_accepts_structurally_valid_allowlisted_meshes(
    tmp_path: Path,
    filename: str,
    content: bytes,
    expected_format: str,
    expected_encoding: str,
    vertices: int,
    faces: int,
    triangles: int,
) -> None:
    path = _write(tmp_path / "staged-upload", content)

    result = preflight_mesh_upload(path, filename)

    assert (result.format, result.encoding) == (expected_format, expected_encoding)
    assert (result.vertex_count, result.face_count, result.triangle_count) == (
        vertices,
        faces,
        triangles,
    )
    serialized = result.to_dict()
    assert serialized["byteSize"] == len(content)
    assert serialized["triangleCount"] == triangles
    assert len(result.sha256) == 64


def test_preflight_rejects_archives_executables_mismatches_and_external_references(
    tmp_path: Path,
) -> None:
    staged = tmp_path / "staged"
    _assert_upload_error(_write(staged, b"PK\x03\x04payload"), "model.stl", "archive_not_allowed")
    _assert_upload_error(
        _write(staged, b"#!/bin/sh\nexit 0\n"),
        "model.obj",
        "executable_not_allowed",
    )
    _assert_upload_error(_write(staged, OBJ_QUAD), "model.stl", "format_mismatch")
    external_obj = b"mtllib ../../secret.mtl\n" + OBJ_QUAD
    _assert_upload_error(
        _write(staged, external_obj), "model.obj", "external_reference_not_allowed"
    )


def test_preflight_rejects_symlinks_bad_counts_and_limits(tmp_path: Path) -> None:
    target = _write(tmp_path / "target", ASCII_STL)
    link = tmp_path / "link"
    link.symlink_to(target)
    _assert_upload_error(link, "model.stl", "symlink_not_allowed")

    malformed_stl = b"binary".ljust(80, b"\0") + struct.pack("<I", 0xFFFFFFFF)
    _assert_upload_error(_write(tmp_path / "bad", malformed_stl), "model.stl", "malformed_mesh")
    _assert_upload_error(
        _write(tmp_path / "large", OBJ_QUAD),
        "model.obj",
        "triangle_limit",
        limits=UploadLimits(max_triangles=1),
    )


def test_preflight_rejects_path_traversal_and_unreasonable_ply_allocations(
    tmp_path: Path,
) -> None:
    staged = _write(tmp_path / "staged", ASCII_PLY)
    _assert_upload_error(staged, "../../part.ply", "unsafe_filename")

    declared_huge = ASCII_PLY.replace(b"element vertex 3", b"element vertex 999999999")
    _assert_upload_error(
        _write(staged, declared_huge),
        "part.ply",
        "vertex_limit",
        limits=UploadLimits(max_vertices=10),
    )


def test_http_policy_normalizes_exact_origins_hosts_and_blocks_injection() -> None:
    assert normalize_origin("HTTPS://Example.COM:443/") == "https://example.com"
    allowed_origins = parse_allowed_origins("https://example.com, http://localhost:5173")
    assert is_origin_allowed("https://EXAMPLE.com", allowed_origins)
    assert require_allowed_origin("https://example.com", allowed_origins) == "https://example.com"
    assert not is_origin_allowed("https://evil.example", allowed_origins)
    with pytest.raises(SecurityPolicyError):
        parse_allowed_origins("*", production=True)
    with pytest.raises(SecurityPolicyError):
        require_allowed_origin("https://evil.example", allowed_origins)

    assert normalize_host("EXAMPLE.com:8443") == "example.com:8443"
    assert parse_allowed_hosts("example.com, localhost") == ("example.com", "localhost")
    assert is_host_allowed("localhost:8000", ("localhost",))
    assert require_allowed_host("example.com:8443", ("example.com:8443",)) == (
        "example.com:8443"
    )
    assert not is_host_allowed("evil.example", ("example.com",))
    with pytest.raises(SecurityPolicyError):
        parse_allowed_hosts("*", production=True)
    with pytest.raises(SecurityPolicyError):
        safe_header_value("safe\r\nX-Evil: true")


def test_security_and_download_headers_are_strict_and_injection_safe() -> None:
    headers = api_security_headers(tls=True)
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" in headers
    display_name = "br\N{LATIN SMALL LETTER A WITH DIAERESIS}cket.stl"
    disposition = attachment_content_disposition(display_name)
    assert disposition.startswith('attachment; filename="bracket.stl";')
    assert "filename*=UTF-8''" in disposition
    with pytest.raises(UnsafeNameError):
        attachment_content_disposition("mesh.stl\r\nX-Evil: true")


def test_symlink_test_is_not_silently_skipped_on_supported_platforms() -> None:
    assert hasattr(os, "symlink")
