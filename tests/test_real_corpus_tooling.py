"""Audit and 3MF-ingest coverage for the ``samples/real`` corpus tooling."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import cadquery as cq
import pytest

# ``scripts`` is a namespace package under the repository root, which is not on the path
# for an installed-package test run.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.real_corpus import audit as audit_module  # noqa: E402
from scripts.real_corpus import corpus, threemf  # noqa: E402
from scripts.real_corpus.audit import (  # noqa: E402
    GENERATED_MESH_ROLES,
    CorpusError,
    PartMetadata,
    audit_directory,
)

THREEMF_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="{unit}" xml:lang="en-US"
       xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="{object_id}" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0" />
          <vertex x="1" y="0" z="0" />
          <vertex x="0" y="1" z="0" />
          <vertex x="0" y="0" z="1" />
        </vertices>
        <triangles>
          <triangle v1="0" v2="2" v3="1" />
          <triangle v1="0" v2="1" v3="3" />
          <triangle v1="0" v2="3" v3="2" />
          <triangle v1="1" v2="2" v3="3" />
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="{object_id}"{transform} />
  </build>
</model>
"""


def write_tetrahedron_3mf(
    path: Path, *, unit: str = "millimeter", object_id: str = "1", transform: str = ""
) -> Path:
    """Write a minimal one-object 3MF package holding a unit tetrahedron."""

    attribute = f' transform="{transform}"' if transform else ""
    model = THREEMF_TEMPLATE.format(unit=unit, object_id=object_id, transform=attribute)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("3D/3dmodel.model", model)
    return path


def build_box_with_hole() -> cq.Shape:
    """A 40x24x8 plate with one 10 mm through hole: six planes plus one cylinder."""

    workplane = cq.Workplane("XY").box(40.0, 24.0, 8.0).faces(">Z").workplane().hole(10.0)
    shape = workplane.val()
    assert isinstance(shape, cq.Shape)
    return shape


def build_split_bore_plate() -> cq.Shape:
    """The hole plate cut in half through the bore axis and fused back without cleaning.

    Exporters often emit a bore as two half-cylinder faces; this reproduces that topology.
    """

    plate = cq.Workplane("XY").box(40.0, 24.0, 8.0).faces(">Z").workplane().hole(10.0)
    lower = plate.split(keepBottom=True)
    upper = plate.split(keepTop=True)
    fused = lower.union(upper, clean=False)
    shape = fused.val()
    assert isinstance(shape, cq.Shape)
    return shape


def build_channel_with_coaxial_holes() -> cq.Shape:
    """A U-channel with one 6 mm hole through each wall on a shared axis."""

    channel = (
        cq.Workplane("XY")
        .box(40.0, 30.0, 20.0)
        .faces(">Z")
        .workplane()
        .rect(40.0, 18.0)
        .cutBlind(-16.0)
    )
    # ProjectedOrigin would land on the wall's top edge; center on the face instead.
    drilled = channel.faces(">Y").workplane(centerOption="CenterOfBoundBox").hole(6.0)
    shape = drilled.val()
    assert isinstance(shape, cq.Shape)
    return shape


@pytest.mark.geometry
def test_split_bore_counts_as_one_hole(tmp_path: Path) -> None:
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopoDS import TopoDS

    from scripts.real_corpus.audit import _sub_shapes, count_holes

    shape = build_split_bore_plate()
    faces = [
        TopoDS.Face_s(face) for face in _sub_shapes(shape.wrapped, TopAbs_ShapeEnum.TopAbs_FACE)
    ]
    cylinders = [face for face in faces if audit_module._surface_name(face) == "cylinder"]
    assert len(cylinders) == 2, "fixture must keep the bore split in two faces"
    assert count_holes(faces) == 1


@pytest.mark.geometry
def test_coaxial_holes_through_separate_walls_count_separately() -> None:
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopoDS import TopoDS

    from scripts.real_corpus.audit import _sub_shapes, count_holes

    shape = build_channel_with_coaxial_holes()
    faces = [
        TopoDS.Face_s(face) for face in _sub_shapes(shape.wrapped, TopAbs_ShapeEnum.TopAbs_FACE)
    ]
    assert count_holes(faces) == 2


@pytest.mark.geometry
def test_audit_reports_box_with_hole_from_disk(tmp_path: Path) -> None:
    directory = tmp_path / "box-with-hole"
    directory.mkdir()
    shape = build_box_with_hole()

    corpus.export_step(shape, directory / "model.step")
    corpus.export_meshes(shape, directory, GENERATED_MESH_ROLES)

    payload = audit_directory(
        directory,
        PartMetadata(
            slug="box-with-hole",
            title="Box With Hole",
            origin="generated",
            license=corpus.REPOSITORY_LICENSE,
            tags=("prismatic",),
        ),
    )

    ground_truth = payload["groundTruth"]
    assert ground_truth is not None
    assert ground_truth["solidCount"] == 1
    # Six planar box walls plus the single cylindrical bore.
    assert ground_truth["faceCount"] == 7
    assert ground_truth["surfaceInventory"] == {"plane": 6, "cylinder": 1}
    assert ground_truth["holeCount"] == 1
    assert payload["featured"] is False

    meshes = payload["meshes"]
    assert [mesh["tessellation"] for mesh in meshes] == ["coarse", "default"]
    for mesh in meshes:
        assert mesh["watertight"], mesh["file"]
        assert mesh["edgeManifold"], mesh["file"]
        assert mesh["windingConsistent"], mesh["file"]
        assert mesh["degenerateFaces"] == 0
        assert mesh["duplicateFaces"] == 0
        assert mesh["sourceFormat"] == "step"
    # Finer tolerances must not lose triangles.
    triangles = [mesh["triangles"] for mesh in meshes]
    assert triangles == sorted(triangles)


@pytest.mark.geometry
def test_step_export_is_byte_identical_across_runs(tmp_path: Path) -> None:
    shape = build_box_with_hole()
    first = corpus.export_step(shape, tmp_path / "first.step")
    second = corpus.export_step(shape, tmp_path / "second.step")
    assert first.read_bytes() == second.read_bytes()
    assert corpus.STEP_EPOCH in first.read_text(encoding="utf-8")


def test_read_3mf_counts_and_millimeter_units(tmp_path: Path) -> None:
    mesh = threemf.read_3mf(write_tetrahedron_3mf(tmp_path / "tetra.3mf"))
    assert mesh.unit == "millimeter"
    assert mesh.vertex_count == 4
    assert mesh.triangle_count == 4
    assert mesh.scaled_to("mm").vertices.max() == pytest.approx(1.0)


def test_read_3mf_scales_inches_into_corpus_units(tmp_path: Path) -> None:
    mesh = threemf.read_3mf(write_tetrahedron_3mf(tmp_path / "inch.3mf", unit="inch"))
    assert mesh.unit == "inch"
    # Declared coordinates stay untouched; only the corpus-unit view is scaled.
    assert mesh.vertices.max() == pytest.approx(1.0)
    assert mesh.scaled_to("mm").vertices.max() == pytest.approx(25.4)
    assert mesh.scaled_to("in").vertices.max() == pytest.approx(1.0)


def test_read_3mf_applies_the_build_transform(tmp_path: Path) -> None:
    path = write_tetrahedron_3mf(tmp_path / "moved.3mf", transform="2 0 0 0 2 0 0 0 2 10 0 0")
    mesh = threemf.read_3mf(path)
    assert mesh.vertices[:, 0].max() == pytest.approx(12.0)
    assert mesh.vertices[:, 0].min() == pytest.approx(10.0)


def test_read_3mf_rejects_a_multi_object_build(tmp_path: Path) -> None:
    path = tmp_path / "two-objects.3mf"
    single = THREEMF_TEMPLATE.format(unit="millimeter", object_id="1", transform="")
    model = single.replace(
        '<item objectid="1" />',
        '<item objectid="1" />\n    <item objectid="7" />',
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("3D/3dmodel.model", model)

    with pytest.raises(CorpusError, match="1, 7"):
        threemf.read_3mf(path)


@pytest.mark.geometry
def test_ingest_3mf_records_source_provenance(tmp_path: Path) -> None:
    source = write_tetrahedron_3mf(tmp_path / "part.3mf", unit="inch")
    directory = corpus.ingest(
        [source],
        tmp_path / "corpus",
        PartMetadata(
            slug="tetra-sample",
            title="Tetra Sample",
            origin="user-export",
            license="CC0-1.0",
            featured=True,
        ),
    )

    payload = corpus.read_part_json(directory)
    assert payload["featured"] is True
    assert payload["groundTruth"] is None
    (mesh,) = payload["meshes"]
    assert mesh["file"] == "mesh-export-3mf.stl"
    assert mesh["tessellation"] == "export"
    assert mesh["sourceFormat"] == "3mf"
    assert mesh["sourceUnit"] == "inch"
    assert mesh["sourceSha256"] == corpus.sha256_file(source)
    assert mesh["triangles"] == 4
    assert mesh["bbox"]["max"][0] == pytest.approx(25.4)

    # An audit from disk must preserve provenance it cannot recompute.
    corpus.audit_all(tmp_path / "corpus")
    assert corpus.read_part_json(directory)["meshes"][0]["sourceFormat"] == "3mf"

    corpus.index(tmp_path / "corpus")
    readme = (tmp_path / "corpus" / "README.md").read_text(encoding="utf-8")
    assert "Featured part" in readme
    assert "**tetra-sample**" in readme
