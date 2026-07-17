"""G0 fixtures and the segmentation gap they are designed to close."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import trimesh
from mesh2param.general_fixtures import (
    CORPUS_MANIFEST_NAME,
    FEATURE_TREE_SCHEMA,
    FIXTURE_MANIFEST_NAME,
    FIXTURE_STL_NAME,
    GENERAL_FIXTURE_SPECS,
    GENERAL_FIXTURES_BY_SLUG,
    generate_general_fixture_corpus,
)
from mesh2param.segmentation import segment_mesh


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("general-parametric-fixtures")
    generate_general_fixture_corpus(root)
    return root


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _manifest(root: Path, slug: str) -> dict[str, Any]:
    payload = json.loads((root / slug / FIXTURE_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _mesh(root: Path, slug: str) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(root / slug / FIXTURE_STL_NAME, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


def test_general_fixture_specs_are_unique() -> None:
    slugs = [spec.slug for spec in GENERAL_FIXTURE_SPECS]
    assert len(slugs) == len(set(slugs))
    assert set(GENERAL_FIXTURES_BY_SLUG) == set(slugs)
    assert {spec.with_fillets for spec in GENERAL_FIXTURE_SPECS} == {False, True}
    assert sum(spec.emboss_depth_mm is not None for spec in GENERAL_FIXTURE_SPECS) == 1


@pytest.mark.geometry
@pytest.mark.samples
def test_general_fixture_corpus_is_byte_stable(corpus: Path, tmp_path: Path) -> None:
    second_root = tmp_path / "second"
    generate_general_fixture_corpus(second_root)
    first_files = _files(corpus)
    second_files = _files(second_root)
    assert set(first_files) == set(second_files)
    for name, payload in first_files.items():
        assert payload == second_files[name], f"{name} is not byte-stable"

    manifest = json.loads((corpus / CORPUS_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["schema"] == FEATURE_TREE_SCHEMA
    assert len(manifest["fixtures"]) == 3
    assert all(not Path(entry["directory"]).is_absolute() for entry in manifest["fixtures"])


@pytest.mark.geometry
@pytest.mark.samples
def test_general_fixtures_are_exact_feature_built_single_bodies(corpus: Path) -> None:
    volumes: dict[str, float] = {}
    for spec in GENERAL_FIXTURE_SPECS:
        mesh = _mesh(corpus, spec.slug)
        assert mesh.is_watertight, spec.slug
        assert mesh.is_winding_consistent, spec.slug
        assert mesh.body_count == 1, spec.slug
        assert np.all(mesh.area_faces > 1e-12), spec.slug

        manifest = _manifest(corpus, spec.slug)
        assert manifest["featureTree"]["schema"] == FEATURE_TREE_SCHEMA
        features = manifest["featureTree"]["features"]
        profile = features[0]
        assert [entity["type"] for entity in profile["entities"]] == [
            "line",
            "threePointArc",
            "line",
            "bsplineInterpolation",
        ]
        assert next(feature for feature in features if feature["id"] == "extrude")["depth"] == 8.0
        hex_cut = next(feature for feature in features if feature["id"] == "hex-cut")
        assert hex_cut["profile"]["sideCount"] == 6
        assert hex_cut["extent"] == "throughAll"

        fillets = [feature for feature in features if feature["id"] == "outer-fillets"]
        assert bool(fillets) is spec.with_fillets
        if fillets:
            assert fillets[0]["radius"] == 1.5
        bosses = [feature for feature in features if feature["id"] == "emboss"]
        assert bool(bosses) is (spec.emboss_depth_mm is not None)
        if bosses:
            assert bosses[0]["depth"] == 0.4

        ground_truth = manifest["groundTruth"]
        assert ground_truth["volume"] > 0.0
        assert (
            ground_truth["faceSurfaces"]["bspline"]
            + ground_truth["faceSurfaces"]["other"]
            >= 1
        )
        volumes[spec.slug] = ground_truth["volume"]

    boss_volume = 18.0 * 6.0 * 0.4
    assert volumes["spanner-filleted-embossed"] - volumes["spanner-filleted"] == pytest.approx(
        # OCCT's adaptive mass integration over the neighboring B-spline and
        # fillet faces contributes a small numerical quadrature error.
        boss_volume,
        abs=0.05,
    )


@pytest.mark.geometry
@pytest.mark.samples
def test_current_segmentation_merges_filleted_spanner_into_one_freeform_region(
    corpus: Path,
) -> None:
    """Document the curvature-discontinuity gap that G1 must close opt-in."""

    mesh = _mesh(corpus, "spanner-filleted")
    segmentation = segment_mesh(mesh)
    assert segmentation.counts_by_type["freeform"] == 1
    freeform = next(patch for patch in segmentation.patches if patch.kind == "freeform")
    # Tangency joins the top, outer fillet bands, outer wall, bottom fillets,
    # and bottom into one smooth region. Only the six sharp hex walls remain
    # outside it as small analytic patches.
    assert len(freeform.triangle_ids) / len(mesh.faces) > 0.99
