from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import trimesh
from mesh2param.comparison import ComparisonSettings, compare_mesh_to_step
from mesh2param.curved_fixtures import (
    CORPUS_MANIFEST_NAME,
    CURVED_FIXTURE_SPECS,
    CURVED_FIXTURES_BY_SLUG,
    FIXTURE_MANIFEST_NAME,
    FIXTURE_STL_NAME,
    generate_curved_fixture_corpus,
)
from mesh2param.faceted import FacetedFallbackError, create_faceted_fallback


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("curved-fixtures")
    generate_curved_fixture_corpus(root)
    return root


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _manifest(corpus_root: Path, slug: str) -> dict[str, Any]:
    payload = json.loads((corpus_root / slug / FIXTURE_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _load_stl(corpus_root: Path, slug: str) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(corpus_root / slug / FIXTURE_STL_NAME, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


def test_fixture_specs_are_unique_and_cover_both_categories() -> None:
    slugs = [spec.slug for spec in CURVED_FIXTURE_SPECS]
    assert len(slugs) == len(set(slugs))
    assert set(CURVED_FIXTURES_BY_SLUG) == set(slugs)
    categories = {spec.category for spec in CURVED_FIXTURE_SPECS}
    assert categories == {"positive", "negative"}
    expectations = {spec.expectation for spec in CURVED_FIXTURE_SPECS}
    assert {
        "closed-manifold",
        "closed-manifold-coarse",
        "open-surface",
        "non-manifold",
        "self-intersecting",
        "multi-body",
    } <= expectations


@pytest.mark.geometry
@pytest.mark.samples
def test_curved_fixture_corpus_is_byte_stable(corpus: Path, tmp_path: Path) -> None:
    second_root = tmp_path / "second"
    generate_curved_fixture_corpus(second_root)
    first_files = _files(corpus)
    second_files = _files(second_root)
    assert set(first_files) == set(second_files)
    for name, payload in first_files.items():
        assert payload == second_files[name], f"{name} is not byte-stable"

    manifest = json.loads((corpus / CORPUS_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert len(manifest["fixtures"]) == len(CURVED_FIXTURE_SPECS)
    for entry in manifest["fixtures"]:
        assert not Path(entry["directory"]).is_absolute()


@pytest.mark.geometry
@pytest.mark.samples
def test_positive_fixtures_are_closed_single_bodies_with_bspline_ground_truth(
    corpus: Path,
) -> None:
    for spec in CURVED_FIXTURE_SPECS:
        if spec.category != "positive":
            continue
        mesh = _load_stl(corpus, spec.slug)
        assert mesh.is_watertight, spec.slug
        assert mesh.is_winding_consistent, spec.slug
        assert mesh.body_count == 1, spec.slug
        assert np.all(mesh.area_faces > 1e-12), spec.slug

        manifest = _manifest(corpus, spec.slug)
        ground_truth = manifest["groundTruth"]
        assert isinstance(ground_truth, dict), spec.slug
        assert ground_truth["faceSurfaces"]["bspline"] >= 1, spec.slug
        assert ground_truth["volume"] > 0.0, spec.slug
        # The whole point of the benchmark: exact ground truth has few faces
        # while the tessellated source has hundreds of triangles.
        assert ground_truth["faceCount"] < 10, spec.slug
        assert manifest["stl"]["triangleCount"] > 20 * ground_truth["faceCount"], spec.slug


@pytest.mark.geometry
@pytest.mark.samples
def test_negative_fixtures_violate_their_declared_rule(corpus: Path) -> None:
    open_sheet = _load_stl(corpus, "open-wavy-sheet")
    assert not open_sheet.is_watertight

    fin = _load_stl(corpus, "non-manifold-fin")
    assert not fin.is_watertight
    _, counts = np.unique(fin.edges_sorted, axis=0, return_counts=True)
    assert counts.max() >= 3  # at least one edge is shared by three faces

    intersecting = _load_stl(corpus, "self-intersecting-boxes")
    assert intersecting.body_count == 2
    bodies = intersecting.split(only_watertight=False)
    minima = np.maximum(bodies[0].bounds[0], bodies[1].bounds[0])
    maxima = np.minimum(bodies[0].bounds[1], bodies[1].bounds[1])
    assert np.all(maxima > minima)  # bounding boxes genuinely overlap

    disjoint = _load_stl(corpus, "multi-body-boxes")
    assert disjoint.body_count == 2
    bodies = disjoint.split(only_watertight=False)
    minima = np.maximum(bodies[0].bounds[0], bodies[1].bounds[0])
    maxima = np.minimum(bodies[0].bounds[1], bodies[1].bounds[1])
    assert np.any(maxima < minima)  # separated along at least one axis

    coarse = _manifest(corpus, "wavy-slab-coarse")
    standard = _manifest(corpus, "wavy-slab")
    assert coarse["stl"]["triangleCount"] < standard["stl"]["triangleCount"]


@pytest.mark.geometry
@pytest.mark.samples
def test_faceted_baseline_builds_one_planar_face_per_triangle(corpus: Path, tmp_path: Path) -> None:
    slug = "wavy-slab-coarse"
    manifest = _manifest(corpus, slug)
    result = create_faceted_fallback(corpus / slug / FIXTURE_STL_NAME, tmp_path, units="mm")
    assert result.step.valid
    # Documents the current face explosion the curved path must beat.
    assert result.step.source.face_count == manifest["stl"]["triangleCount"]

    source_mesh = _load_stl(corpus, slug)
    comparison = compare_mesh_to_step(
        source_mesh,
        result.step.path,
        units="mm",
        settings=ComparisonSettings(sample_count_each_direction=200),
    )
    assert comparison.maximum_distance_mm < 1e-3


@pytest.mark.geometry
@pytest.mark.samples
def test_faceted_baseline_rejects_unqualified_meshes(corpus: Path, tmp_path: Path) -> None:
    for slug in ("open-wavy-sheet", "non-manifold-fin"):
        with pytest.raises(FacetedFallbackError):
            create_faceted_fallback(corpus / slug / FIXTURE_STL_NAME, tmp_path / slug, units="mm")
