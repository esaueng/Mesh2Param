"""Deterministic feature-built fixtures for general parametric reconstruction.

The G-series corpus is deliberately separate from the curved-plate benchmark:
adding these real-part fixtures must not change any historical plate fixture or
manifest byte.  Every solid is built from the same recorded CadQuery feature
tree, then tessellated to an STL that future general reconstruction milestones
can score against the exact kernel ground truth.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cadquery as cq
import numpy as np
import trimesh

from .tessellation import tessellate_shape
from .validation import classify_face_surfaces, validate_shape

FIXTURE_STL_NAME = "source.stl"
FIXTURE_MANIFEST_NAME = "fixture.json"
CORPUS_MANIFEST_NAME = "manifest.json"

PROFILE_START = (-35.0, -10.0)
PROFILE_LINE_1_END = (25.0, -10.0)
PROFILE_ARC_THROUGH = (35.0, 0.0)
PROFILE_ARC_END = (25.0, 10.0)
PROFILE_LINE_2_END = (-35.0, 10.0)
PROFILE_BSPLINE_POINTS = (
    (-42.0, 9.0),
    (-48.0, 5.0),
    (-50.0, 0.0),
    (-48.0, -5.0),
    (-42.0, -9.0),
    PROFILE_START,
)
PROFILE_BSPLINE_TANGENTS = ((-1.0, 0.0), (1.0, 0.0))

EXTRUDE_DEPTH_MM = 8.0
FILLET_RADIUS_MM = 1.5
HEX_CENTER = (25.0, 0.0)
HEX_SIDES = 6
HEX_CIRCUMDIAMETER_MM = 12.0
EMBOSS_CENTER = (-5.0, 0.0)
EMBOSS_WIDTH_MM = 18.0
EMBOSS_HEIGHT_MM = 6.0
EMBOSS_DEPTH_MM = 0.4

FEATURE_TREE_SCHEMA = "mesh2param/general-parametric-fixture/1"


@dataclass(frozen=True, slots=True)
class GeneralFixtureSpec:
    """One exact feature-tree variant and its deterministic tessellation."""

    slug: str
    title: str
    description: str
    with_fillets: bool
    emboss_depth_mm: float | None = None
    linear_tolerance: float = 0.005
    angular_tolerance: float = 0.18

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "family": "general-parametric",
            "category": "positive",
            "expectation": "closed-manifold",
            "description": self.description,
            "units": "mm",
            "tessellation": {
                "linearTolerance": self.linear_tolerance,
                "angularTolerance": self.angular_tolerance,
            },
            "featureTree": _feature_tree(self),
        }


GENERAL_FIXTURE_SPECS: tuple[GeneralFixtureSpec, ...] = (
    GeneralFixtureSpec(
        slug="spanner-filleted",
        title="Filleted ring spanner",
        description=(
            "A line, circular-arc, and B-spline profile extruded 8 mm, with "
            "1.5 mm outer top/bottom fillets and one hexagonal through-cut."
        ),
        with_fillets=True,
    ),
    GeneralFixtureSpec(
        slug="spanner-sharp",
        title="Sharp ring spanner",
        description=(
            "The same line, circular-arc, and B-spline profile and hexagonal "
            "through-cut, with the top and bottom fillet feature omitted."
        ),
        with_fillets=False,
    ),
    GeneralFixtureSpec(
        slug="spanner-filleted-embossed",
        title="Filleted ring spanner with shallow boss",
        description=(
            "The filleted spanner with an additional 18 x 6 x 0.4 mm "
            "rectangular boss on the top handle face."
        ),
        with_fillets=True,
        emboss_depth_mm=EMBOSS_DEPTH_MM,
    ),
)

GENERAL_FIXTURES_BY_SLUG: dict[str, GeneralFixtureSpec] = {
    spec.slug: spec for spec in GENERAL_FIXTURE_SPECS
}


def _profile_entities() -> list[dict[str, Any]]:
    """Return the exact ordered inputs used to construct the closed sketch."""

    return [
        {
            "id": "profile-line-0",
            "type": "line",
            "start": list(PROFILE_START),
            "end": list(PROFILE_LINE_1_END),
        },
        {
            "id": "profile-arc-0",
            "type": "threePointArc",
            "start": list(PROFILE_LINE_1_END),
            "through": list(PROFILE_ARC_THROUGH),
            "end": list(PROFILE_ARC_END),
        },
        {
            "id": "profile-line-1",
            "type": "line",
            "start": list(PROFILE_ARC_END),
            "end": list(PROFILE_LINE_2_END),
        },
        {
            "id": "profile-bspline-0",
            "type": "bsplineInterpolation",
            "start": list(PROFILE_LINE_2_END),
            "interpolationPoints": [list(point) for point in PROFILE_BSPLINE_POINTS],
            "endTangents": [list(tangent) for tangent in PROFILE_BSPLINE_TANGENTS],
            "periodic": False,
            "scaleTangents": True,
        },
    ]


def _feature_tree(spec: GeneralFixtureSpec) -> dict[str, Any]:
    features: list[dict[str, Any]] = [
        {
            "id": "profile",
            "type": "sketchProfile",
            "plane": "XY",
            "closed": True,
            "entities": _profile_entities(),
        },
        {
            "id": "extrude",
            "type": "extrude",
            "inputFeatureId": "profile",
            "depth": EXTRUDE_DEPTH_MM,
            "direction": [0.0, 0.0, 1.0],
        },
    ]
    previous_feature_id = "extrude"
    if spec.with_fillets:
        features.append(
            {
                "id": "outer-fillets",
                "type": "fillet",
                "inputFeatureId": previous_feature_id,
                "radius": FILLET_RADIUS_MM,
                "edgeSelection": {
                    "kind": "outerTopAndBottomLoops",
                    "cadquerySelector": ">Z or <Z",
                    "deterministicOrder": "centerZXYThenLength",
                },
            }
        )
        previous_feature_id = "outer-fillets"
    features.append(
        {
            "id": "hex-cut",
            "type": "cutExtrude",
            "inputFeatureId": previous_feature_id,
            "profile": {
                "type": "regularPolygon",
                "plane": "topFace",
                "center": list(HEX_CENTER),
                "sideCount": HEX_SIDES,
                "circumdiameter": HEX_CIRCUMDIAMETER_MM,
                "circumscribed": False,
                "firstVertexDirection": [1.0, 0.0],
            },
            "extent": "throughAll",
            "direction": [0.0, 0.0, -1.0],
        }
    )
    if spec.emboss_depth_mm is not None:
        features.append(
            {
                "id": "emboss",
                "type": "bossExtrude",
                "inputFeatureId": "hex-cut",
                "profile": {
                    "type": "centeredRectangle",
                    "plane": "topFace",
                    "center": list(EMBOSS_CENTER),
                    "width": EMBOSS_WIDTH_MM,
                    "height": EMBOSS_HEIGHT_MM,
                },
                "depth": spec.emboss_depth_mm,
                "direction": [0.0, 0.0, 1.0],
            }
        )
    return {
        "schema": FEATURE_TREE_SCHEMA,
        "units": "mm",
        "modelingSystem": {"library": "cadquery", "version": "2.8.0"},
        "features": features,
    }


def _spanner_profile() -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .moveTo(*PROFILE_START)
        .lineTo(*PROFILE_LINE_1_END)
        .threePointArc(PROFILE_ARC_THROUGH, PROFILE_ARC_END)
        .lineTo(*PROFILE_LINE_2_END)
        .spline(
            PROFILE_BSPLINE_POINTS,
            tangents=PROFILE_BSPLINE_TANGENTS,
            periodic=False,
            scale=True,
            includeCurrent=True,
        )
        .close()
    )


def build_general_fixture_shape(spec: GeneralFixtureSpec) -> cq.Shape:
    """Replay one fixture's recorded feature tree through CadQuery."""

    model = _spanner_profile().extrude(EXTRUDE_DEPTH_MM)
    if spec.with_fillets:
        base = model.val()
        if not isinstance(base, cq.Solid):
            raise TypeError(f"extrude returned {type(base).__name__}, not a CadQuery solid")
        edge_plane_epsilon = 1e-8
        loop_edges = [
            edge
            for edge in base.Edges()
            if abs(edge.Center().z) <= edge_plane_epsilon
            or abs(edge.Center().z - EXTRUDE_DEPTH_MM) <= edge_plane_epsilon
        ]
        # BRepFilletAPI is order-sensitive for mixed line/arc/B-spline loops.
        # Topology iteration order is not a stable contract, so sort the exact
        # selected edges geometrically before applying the single fillet feature.
        loop_edges.sort(
            key=lambda edge: (
                round(edge.Center().z, 9),
                round(edge.Center().x, 9),
                round(edge.Center().y, 9),
                round(edge.Length(), 9),
            )
        )
        if len(loop_edges) != 8:
            raise ValueError(f"expected 8 outer top/bottom edges, found {len(loop_edges)}")
        filleted = base.fillet(FILLET_RADIUS_MM, loop_edges)
        model = cq.Workplane("XY").newObject([filleted])
    model = (
        model.faces(">Z")
        .workplane(origin=(0.0, 0.0, EXTRUDE_DEPTH_MM))
        .center(*HEX_CENTER)
        .polygon(HEX_SIDES, HEX_CIRCUMDIAMETER_MM, circumscribed=False)
        .cutThruAll()
    )
    if spec.emboss_depth_mm is not None:
        model = (
            model.faces(">Z")
            .workplane(origin=(0.0, 0.0, EXTRUDE_DEPTH_MM))
            .center(*EMBOSS_CENTER)
            .rect(EMBOSS_WIDTH_MM, EMBOSS_HEIGHT_MM)
            .extrude(spec.emboss_depth_mm)
        )
    shape = model.val()
    if not isinstance(shape, cq.Shape):
        raise TypeError(f"feature replay returned {type(shape).__name__}, not a CadQuery shape")
    return shape


def _welded(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    return trimesh.Trimesh(
        vertices=np.asarray(mesh.vertices, dtype=np.float64),
        faces=np.asarray(mesh.faces, dtype=np.int64),
        process=True,
        validate=False,
    )


def _mesh_from_shape(spec: GeneralFixtureSpec, shape: cq.Shape) -> trimesh.Trimesh:
    tessellation = tessellate_shape(
        shape,
        linear_tolerance=spec.linear_tolerance,
        angular_tolerance=spec.angular_tolerance,
    )
    return _welded(
        trimesh.Trimesh(
            vertices=np.asarray(tessellation.vertices, dtype=np.float64),
            faces=np.asarray(tessellation.triangles, dtype=np.int64),
            process=False,
            validate=False,
        )
    )


def _ground_truth_summary(shape: cq.Shape) -> dict[str, Any]:
    validation = validate_shape(shape, require_tessellation=False)
    bbox = shape.BoundingBox()
    return {
        "volume": validation.volume,
        "area": validation.area,
        "faceCount": validation.face_count,
        "edgeCount": validation.edge_count,
        "faceSurfaces": classify_face_surfaces(shape),
        "boundingBox": [bbox.xmin, bbox.ymin, bbox.zmin, bbox.xmax, bbox.ymax, bbox.zmax],
    }


@dataclass(frozen=True, slots=True)
class GeneratedGeneralFixture:
    spec: GeneralFixtureSpec
    directory: str
    stl_sha256: str
    stl_byte_size: int
    triangle_count: int
    vertex_count: int
    ground_truth: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.spec.to_dict(),
            "directory": self.directory,
            "stl": {
                "path": FIXTURE_STL_NAME,
                "sha256": self.stl_sha256,
                "byteSize": self.stl_byte_size,
                "triangleCount": self.triangle_count,
                "vertexCount": self.vertex_count,
            },
            "mesh": {
                "watertight": True,
                "windingConsistent": True,
                "bodyCount": 1,
            },
            "groundTruth": self.ground_truth,
        }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate_general_fixture(
    spec: GeneralFixtureSpec, output_root: str | Path
) -> GeneratedGeneralFixture:
    shape = build_general_fixture_shape(spec)
    mesh = _mesh_from_shape(spec, shape)
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.body_count != 1:
        raise ValueError(f"{spec.slug} did not tessellate to one closed consistently wound body")

    directory = Path(output_root) / spec.slug
    directory.mkdir(parents=True, exist_ok=True)
    stl_path = directory / FIXTURE_STL_NAME
    payload = mesh.export(file_type="stl")
    if not isinstance(payload, bytes):
        raise TypeError(f"binary STL export returned {type(payload).__name__}, not bytes")
    stl_path.write_bytes(payload)

    generated = GeneratedGeneralFixture(
        spec=spec,
        directory=spec.slug,
        stl_sha256=hashlib.sha256(payload).hexdigest(),
        stl_byte_size=len(payload),
        triangle_count=len(mesh.faces),
        vertex_count=len(mesh.vertices),
        ground_truth=_ground_truth_summary(shape),
    )
    _write_json(directory / FIXTURE_MANIFEST_NAME, generated.to_dict())
    return generated


def generate_general_fixture_corpus(
    output_root: str | Path, slugs: Sequence[str] | None = None
) -> list[GeneratedGeneralFixture]:
    selected = GENERAL_FIXTURE_SPECS
    if slugs is not None:
        unknown = sorted(set(slugs) - set(GENERAL_FIXTURES_BY_SLUG))
        if unknown:
            raise KeyError(f"unknown general fixture slugs: {', '.join(unknown)}")
        requested = set(slugs)
        selected = tuple(spec for spec in GENERAL_FIXTURE_SPECS if spec.slug in requested)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    generated = [generate_general_fixture(spec, root) for spec in selected]
    if slugs is None:
        _write_json(
            root / CORPUS_MANIFEST_NAME,
            {"schema": FEATURE_TREE_SCHEMA, "fixtures": [item.to_dict() for item in generated]},
        )
    return generated


__all__ = [
    "CORPUS_MANIFEST_NAME",
    "FEATURE_TREE_SCHEMA",
    "FIXTURE_MANIFEST_NAME",
    "FIXTURE_STL_NAME",
    "GENERAL_FIXTURES_BY_SLUG",
    "GENERAL_FIXTURE_SPECS",
    "GeneralFixtureSpec",
    "GeneratedGeneralFixture",
    "build_general_fixture_shape",
    "generate_general_fixture",
    "generate_general_fixture_corpus",
]
