"""G2b deterministic section-stack and fillet-radius evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import trimesh
from mesh2param.reconstruction import ReconstructionError, reconstruct_file
from mesh2param.sections import extract_section_stack, write_section_debug_glb

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPOSITORY_ROOT / "samples" / "general-parametric-benchmark"


def _mesh(slug: str) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(_FIXTURES / slug / "source.stl", process=False)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


@pytest.mark.geometry
def test_sharp_mid_section_has_closed_outer_and_hex_inner_loops() -> None:
    source = _mesh("spanner-sharp")
    source_vertices = np.asarray(source.vertices).copy()
    source_faces = np.asarray(source.faces).copy()
    first = extract_section_stack(source)
    second = extract_section_stack(_mesh("spanner-sharp"))

    np.testing.assert_array_equal(source.vertices, source_vertices)
    np.testing.assert_array_equal(source.faces, source_faces)
    assert first.to_dict() == second.to_dict()
    assert first.primary_extent_mm == pytest.approx(8.0, abs=1e-3)
    assert len(first.reference_slice.loops) == 2
    outer, inner = first.reference_slice.loops
    assert not outer.is_hole
    assert inner.is_hole
    assert inner.corner_count == 6
    assert outer.closure_error_mm < 0.01
    assert inner.closure_error_mm < 0.01
    np.testing.assert_allclose(outer.array[0], outer.array[-1], atol=1e-12)
    np.testing.assert_allclose(inner.array[0], inner.array[-1], atol=1e-12)
    assert first.section_to_section_deviation_mm >= 0.0
    assert not first.radius_fit.accepted
    assert first.diagnostics == ()
    assert all(section.source_triangle_ids for section in first.slices)


@pytest.mark.geometry
@pytest.mark.parametrize("slug", ("spanner-filleted", "spanner-filleted-embossed"))
def test_filleted_section_inset_fits_recorded_circle_radius(slug: str) -> None:
    stack = extract_section_stack(_mesh(slug))

    assert stack.primary_extent_mm == pytest.approx(8.0, abs=1e-3)
    assert len(stack.reference_slice.loops) == 2
    assert stack.reference_slice.loops[1].corner_count == 6
    assert stack.radius_fit.accepted
    assert stack.radius_fit.radius_mm == pytest.approx(1.5, abs=0.1)
    assert stack.radius_fit.rms_residual_mm is not None
    assert stack.radius_fit.rms_residual_mm < 0.03
    assert stack.radius_fit.maximum_residual_mm is not None
    assert stack.radius_fit.maximum_residual_mm < 0.08
    assert max(sample.measured_inset_mm for sample in stack.radius_fit.samples) > 0.6
    assert [diagnostic.code for diagnostic in stack.diagnostics] == ["fillet-band-detected"]


@pytest.mark.geometry
def test_rotated_section_stack_preserves_radius_and_debug_hash(tmp_path: Path) -> None:
    mesh = _mesh("spanner-filleted")
    transform = trimesh.transformations.rotation_matrix(0.71, (1.0, -2.0, 0.5))
    transform[:3, 3] = np.asarray((17.0, -8.0, 4.0))
    mesh.apply_transform(transform)

    first = extract_section_stack(mesh)
    second = extract_section_stack(mesh.copy())
    assert first.to_dict() == second.to_dict()
    assert first.radius_fit.accepted
    assert first.radius_fit.radius_mm == pytest.approx(1.5, abs=0.1)

    first_path = tmp_path / "sections-first.glb"
    second_path = tmp_path / "sections-second.glb"
    write_section_debug_glb(first, first_path)
    write_section_debug_glb(second, second_path)
    assert (
        hashlib.sha256(first_path.read_bytes()).digest()
        == hashlib.sha256(second_path.read_bytes()).digest()
    )
    assert first_path.read_bytes()[:4] == b"glTF"


@pytest.mark.geometry
def test_reconstruction_persists_deterministic_section_artifacts(tmp_path: Path) -> None:
    outputs = (tmp_path / "first", tmp_path / "second")
    for output in outputs:
        with pytest.raises(ReconstructionError) as excinfo:
            reconstruct_file(
                _FIXTURES / "spanner-filleted" / "source.stl",
                output,
                units="mm",
            )
        assert excinfo.value.code == "fillet-band-detected"

    for artifact in ("sections.json", "sections.glb"):
        first_hash = hashlib.sha256((outputs[0] / artifact).read_bytes()).digest()
        second_hash = hashlib.sha256((outputs[1] / artifact).read_bytes()).digest()
        assert first_hash == second_hash
