from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
from mesh2param.samples import SAMPLE_SPECS, generate_sample_corpus
from mesh2param_contracts import CADGraph

EXPECTED_FILES = {
    "manifest.json",
    "metadata.json",
    "model.cadgraph.json",
    "model.cq.py",
    "model.glb",
    "model.step",
    "source-high.stl",
    "source-low.stl",
    "source-random.stl",
    "thumbnail.svg",
}


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _assert_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(path, file_type="stl", process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    assert loaded.body_count == 1
    assert loaded.is_watertight
    assert loaded.is_winding_consistent
    assert np.all(loaded.area_faces > 1e-12)
    return loaded


@pytest.mark.geometry
@pytest.mark.samples
def test_full_sample_corpus_roundtrips_and_is_byte_stable(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = generate_sample_corpus(first_root)
    second = generate_sample_corpus(second_root)
    assert len(first) == len(second) == len(SAMPLE_SPECS) == 10
    assert _files(first_root) == _files(second_root)

    for spec in SAMPLE_SPECS:
        directory = first_root / spec.slug
        assert {path.name for path in directory.iterdir()} == EXPECTED_FILES
        graph = CADGraph.model_validate_json(
            (directory / "model.cadgraph.json").read_text(encoding="utf-8")
        )
        assert graph.validation.status == "valid"
        high_payload = (directory / "source-high.stl").read_bytes()
        assert graph.source is not None
        assert graph.source.sha256 == hashlib.sha256(high_payload).hexdigest()
        assert graph.source.byte_size == len(high_payload)

        high = _assert_mesh(directory / "source-high.stl")
        low = _assert_mesh(directory / "source-low.stl")
        random = _assert_mesh(directory / "source-random.stl")
        assert len(low.faces) <= len(high.faces)
        assert len(random.faces) == len(high.faces)

        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        for artifact in manifest["artifacts"]:
            path = directory / artifact["name"]
            assert path.stat().st_size == artifact["byteSize"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
