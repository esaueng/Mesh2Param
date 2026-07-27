"""Authoritative deterministic CADGraph definitions for the M1 sample corpus."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from mesh2param_contracts import CADGraph, canonical_json

SAMPLE_SEED_BASE = 0x4D325000
FIXED_TIMESTAMP = "1970-01-01T00:00:00Z"
ZERO_SHA256 = "0" * 64
AUTOMATIC_RECONSTRUCTION_SAMPLE_SCOPE = (
    "Automatic inference currently supports only the L-bracket with four through holes."
)


@dataclass(frozen=True, slots=True)
class SampleSpec:
    """Expected exact geometry and artifact identity for one procedural sample."""

    slug: str
    name: str
    ordinal: int
    expected_bbox: tuple[float, float, float, float, float, float]
    expected_volume: float
    expected_planar_faces: int
    expected_cylindrical_faces: int
    factory: Callable[[SampleSpec], CADGraph]
    automatic_reconstruction_supported: bool = False

    @property
    def seed(self) -> int:
        return SAMPLE_SEED_BASE + self.ordinal

    def graph(self) -> CADGraph:
        return self.factory(self)


@dataclass(frozen=True, slots=True)
class SampleTransform:
    """Frozen seeded rigid transform applied to a sample's random source mesh."""

    angles_deg: tuple[float, float, float]
    translation_mm: tuple[float, float, float]
    rotation: tuple[tuple[float, float, float], ...]


def sample_transform(spec: SampleSpec) -> SampleTransform:
    """Draw the directive's deterministic Rx/Ry/Rz and translation values."""

    rng = np.random.Generator(np.random.PCG64(spec.seed))
    angles = (
        float(rng.integers(-300, 301)) / 10,
        float(rng.integers(-300, 301)) / 10,
        float(rng.integers(-600, 601)) / 10,
    )
    translation = tuple(float(rng.integers(-250, 251)) / 10 for _ in range(3))
    rx, ry, rz = np.radians(np.asarray(angles, dtype=np.float64))
    rotation_x = np.asarray(((1, 0, 0), (0, np.cos(rx), -np.sin(rx)), (0, np.sin(rx), np.cos(rx))))
    rotation_y = np.asarray(((np.cos(ry), 0, np.sin(ry)), (0, 1, 0), (-np.sin(ry), 0, np.cos(ry))))
    rotation_z = np.asarray(((np.cos(rz), -np.sin(rz), 0), (np.sin(rz), np.cos(rz), 0), (0, 0, 1)))
    rotation = rotation_z @ rotation_y @ rotation_x
    return SampleTransform(
        angles_deg=angles,
        translation_mm=cast(tuple[float, float, float], translation),
        rotation=cast(
            tuple[tuple[float, float, float], ...],
            tuple(tuple(round(float(item), 12) for item in row) for row in rotation),
        ),
    )


def _entity_fields(entity_id: str) -> dict[str, Any]:
    return {
        "id": entity_id,
        "construction": False,
        "sourceEvidence": ["evidence.generated"],
        "confidence": 1.0,
        "locked": False,
        "suppressed": False,
    }


def _rectangle(entity_id: str, x: float, y: float, width: float, height: float) -> dict[str, Any]:
    return {
        **_entity_fields(entity_id),
        "kind": "rectangle",
        "origin": {"x": x, "y": y},
        "width": width,
        "height": height,
        "rotationDeg": 0.0,
    }


def _circle(entity_id: str, x: float, y: float, radius: float) -> dict[str, Any]:
    return {
        **_entity_fields(entity_id),
        "kind": "circle",
        "center": {"x": x, "y": y},
        "radius": radius,
    }


def _polyline(entity_id: str, points: list[tuple[float, float]]) -> dict[str, Any]:
    return {
        **_entity_fields(entity_id),
        "kind": "polyline",
        "points": [{"x": x, "y": y} for x, y in points],
        "closed": True,
    }


def _sketch(
    sketch_id: str,
    name: str,
    *,
    origin: tuple[float, float, float],
    normal: tuple[float, float, float],
    x_axis: tuple[float, float, float],
    entity: dict[str, Any],
) -> dict[str, Any]:
    profile_id = f"{sketch_id}.profile"
    return {
        "id": sketch_id,
        "name": name,
        "plane": {
            "origin": _vector3(origin),
            "normal": _vector3(normal),
            "xAxis": _vector3(x_axis),
        },
        "entities": [entity],
        "constraints": [],
        "profiles": [
            {
                "id": profile_id,
                "name": f"{name} profile",
                "outerLoop": [entity["id"]],
                "innerLoops": [],
                "orientation": "counterclockwise",
                "closed": True,
                "sourceEvidence": ["evidence.generated"],
                "confidence": 1.0,
                "locked": False,
            }
        ],
        "sourceEvidence": ["evidence.generated"],
        "confidence": 1.0,
        "userLocks": [],
        "overrides": [],
        "suppressed": False,
    }


def _xy_rectangle_sketch(
    sketch_id: str,
    name: str,
    width: float,
    height: float,
    *,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
) -> dict[str, Any]:
    return _sketch(
        sketch_id,
        name,
        origin=(0.0, 0.0, z),
        normal=(0.0, 0.0, 1.0),
        x_axis=(1.0, 0.0, 0.0),
        entity=_rectangle(f"{sketch_id}.rectangle", x, y, width, height),
    )


def _xy_circle_sketch(sketch_id: str, name: str, radius: float) -> dict[str, Any]:
    return _sketch(
        sketch_id,
        name,
        origin=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        x_axis=(1.0, 0.0, 0.0),
        entity=_circle(f"{sketch_id}.circle", 0.0, 0.0, radius),
    )


def _xz_revolution_sketch(
    sketch_id: str, name: str, points: list[tuple[float, float]]
) -> dict[str, Any]:
    return _sketch(
        sketch_id,
        name,
        origin=(0.0, 0.0, 0.0),
        normal=(0.0, -1.0, 0.0),
        x_axis=(1.0, 0.0, 0.0),
        entity=_polyline(f"{sketch_id}.polyline", points),
    )


def _feature_fields(
    feature_id: str,
    name: str,
    order: int,
    dependencies: list[str],
) -> dict[str, Any]:
    return {
        "id": feature_id,
        "name": name,
        "order": order,
        "dependencies": dependencies,
        "suppressed": False,
        "sourceEvidence": ["evidence.generated"],
        "confidence": 1.0,
        "userLocks": [],
        "overrides": [],
        "semanticOutputs": [f"{feature_id}.result"],
    }


def _extrusion(
    feature_id: str,
    name: str,
    order: int,
    sketch_id: str,
    direction: tuple[float, float, float],
    distance: float,
    *,
    mode: str = "base",
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    return {
        **_feature_fields(feature_id, name, order, dependencies or []),
        "operation": "extrusion",
        "booleanMode": mode,
        "sketchId": sketch_id,
        "profileIds": [f"{sketch_id}.profile"],
        "direction": _vector3(direction),
        "extent": "blind",
        "distance": distance,
    }


def _revolution(
    feature_id: str,
    name: str,
    order: int,
    sketch_id: str,
    *,
    mode: str = "base",
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    return {
        **_feature_fields(feature_id, name, order, dependencies or []),
        "operation": "revolution",
        "booleanMode": mode,
        "sketchId": sketch_id,
        "profileIds": [f"{sketch_id}.profile"],
        "axis": {
            "origin": _vector3((0.0, 0.0, 0.0)),
            "direction": _vector3((0.0, 0.0, 1.0)),
        },
        "angleDeg": 360.0,
    }


def _hole(
    feature_id: str,
    name: str,
    order: int,
    position: tuple[float, float, float],
    axis: tuple[float, float, float],
    diameter: float,
    *,
    depth: float | None = None,
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    feature: dict[str, Any] = {
        **_feature_fields(feature_id, name, order, dependencies or []),
        "operation": "hole",
        "booleanMode": "subtractive",
        "holeType": "blind" if depth is not None else "through",
        "position": _vector3(position),
        "axis": _vector3(axis),
        "diameter": diameter,
    }
    if depth is not None:
        feature["depth"] = depth
    return feature


def _pocket(
    feature_id: str,
    name: str,
    order: int,
    sketch_id: str,
    depth: float,
    dependencies: list[str],
) -> dict[str, Any]:
    return {
        **_feature_fields(feature_id, name, order, dependencies),
        "operation": "pocket",
        "booleanMode": "subtractive",
        "sketchId": sketch_id,
        "profileIds": [f"{sketch_id}.profile"],
        "direction": _vector3((0.0, 0.0, -1.0)),
        "extent": "blind",
        "depth": depth,
    }


def _linear_pattern(
    feature_id: str,
    name: str,
    order: int,
    source_feature_id: str,
    direction: tuple[float, float, float],
    count: int,
    spacing: float,
) -> dict[str, Any]:
    return {
        **_feature_fields(feature_id, name, order, [source_feature_id]),
        "operation": "linearPattern",
        "sourceFeatureIds": [source_feature_id],
        "direction": _vector3(direction),
        "count": count,
        "spacing": spacing,
    }


def _circular_pattern(
    feature_id: str,
    name: str,
    order: int,
    source_feature_id: str,
    count: int,
    total_angle_deg: float,
) -> dict[str, Any]:
    return {
        **_feature_fields(feature_id, name, order, [source_feature_id]),
        "operation": "circularPattern",
        "sourceFeatureIds": [source_feature_id],
        "axis": {
            "origin": _vector3((0.0, 0.0, 0.0)),
            "direction": _vector3((0.0, 0.0, 1.0)),
        },
        "count": count,
        "totalAngleDeg": total_angle_deg,
    }


def _vector3(values: tuple[float, float, float]) -> dict[str, float]:
    x, y, z = values
    return {"x": float(x), "y": float(y), "z": float(z)}


def _topology(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{feature['id']}.result",
            "kind": "solid",
            "producerFeatureId": feature["id"],
            "role": "resultSolid",
            "generatedFrom": list(feature.get("profileIds", feature.get("sourceFeatureIds", []))),
            "status": "unresolved",
        }
        for feature in features
    ]


def _graph(
    spec: SampleSpec,
    sketches: list[dict[str, Any]],
    features: list[dict[str, Any]],
) -> CADGraph:
    document: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "id": f"sample.{spec.slug}",
        "name": spec.name,
        "units": "mm",
        "source": {
            "format": "generated",
            "sha256": ZERO_SHA256,
            "originalFileName": "source-high.stl",
            "byteSize": 0,
            "triangleCount": 0,
            "declaredUnits": "mm",
            "scaleFactor": 1.0,
        },
        "sourceCoordinateFrame": {
            "origin": _vector3((0.0, 0.0, 0.0)),
            "xAxis": _vector3((1.0, 0.0, 0.0)),
            "yAxis": _vector3((0.0, 1.0, 0.0)),
            "zAxis": _vector3((0.0, 0.0, 1.0)),
            "locked": True,
            "confidence": 1.0,
            "evidenceIds": ["evidence.generated"],
        },
        "projectTolerance": {
            "surfaceDeviation": 0.15,
            "angularDeviationDeg": 2.0,
            "linearResolution": 0.000001,
        },
        "sketches": sketches,
        "features": features,
        "semanticTopology": _topology(features),
        "sourceEvidence": [
            {
                "id": "evidence.generated",
                "sourceType": "derived",
                "sourceIds": [],
                "confidence": 1.0,
                "notes": "Deterministic procedural M1 sample",
            }
        ],
        "userLocks": [],
        "overrides": [],
        "reconstructionSettings": {
            "maxFeatures": 64,
            "beamWidth": 3,
            "candidatesPerResidual": 4,
            "wallClockSeconds": 300.0,
            "maxRebuilds": 200,
            "minScoreImprovement": 0.001,
            "nominalSnappingEnabled": True,
            "nominalSnapTolerance": 0.1,
            "scoreWeights": {
                "rmsDistance": 1.0,
                "p95Distance": 1.0,
                "maxDistance": 0.5,
                "normalAgreement": 0.5,
                "volumeDifference": 0.75,
                "overlap": 0.75,
                "sharpEdgeAlignment": 0.5,
                "boundaryAlignment": 0.5,
                "unmatchedSource": 1.0,
                "excessResult": 1.0,
                "complexity": 0.1,
                "unsupportedOperation": 2.0,
                "evidenceConfidence": 0.25,
            },
        },
        "engineVersions": {
            "mesh2param": "0.1.0",
            "contracts": "1.0.0",
            "cadBackend": "OCCT",
            "cadQuery": "2.8.0",
            "ocp": "7.9.3.1.1",
            "dependencies": {
                "numpy": "2.4.6",
                "trimesh": "4.12.2",
            },
        },
        "deterministicSeed": spec.seed,
        "fitMetrics": {
            "rmsSurfaceDistance": 0.0,
            "p95SurfaceDistance": 0.0,
            "maxSurfaceDistance": 0.0,
            "normalAgreement": 1.0,
            "volumeDifference": 0.0,
            "overlap": 1.0,
            "unmatchedSourceArea": 0.0,
            "excessResultArea": 0.0,
            "score": 1.0,
        },
        "validation": {
            "status": "notRun",
            "brepValid": None,
            "stepReimportValid": None,
            "toleranceSatisfied": None,
            "lastValidFeatureId": None,
            "issues": [],
        },
        "versionMetadata": {
            "versionId": f"version.{spec.slug}",
            "createdAt": FIXED_TIMESTAMP,
            "createdBy": "mesh2param-samples",
            "message": "Deterministic M1 procedural sample",
        },
        "extensions": {
            "mesh2param.dev/sample": {
                "slug": spec.slug,
                "expectedBbox": list(spec.expected_bbox),
                "expectedVolume": spec.expected_volume,
                "expectedPlanarFaces": spec.expected_planar_faces,
                "expectedCylindricalFaces": spec.expected_cylindrical_faces,
            }
        },
    }
    return CADGraph.model_validate(document)


def _rectangular_block(spec: SampleSpec) -> CADGraph:
    sketch = _xy_rectangle_sketch("sketch.base", "Base", 40.0, 30.0)
    features = [_extrusion("feature.base", "Base extrusion", 0, "sketch.base", (0, 0, 1), 12.0)]
    return _graph(spec, [sketch], features)


def _block_through_hole(spec: SampleSpec) -> CADGraph:
    sketch = _xy_rectangle_sketch("sketch.base", "Base", 40.0, 30.0)
    features = [
        _extrusion("feature.base", "Base extrusion", 0, "sketch.base", (0, 0, 1), 12.0),
        _hole(
            "feature.hole",
            "Through hole",
            1,
            (20, 15, 12),
            (0, 0, -1),
            8.0,
            dependencies=["feature.base"],
        ),
    ]
    return _graph(spec, [sketch], features)


def _block_blind_hole(spec: SampleSpec) -> CADGraph:
    sketch = _xy_rectangle_sketch("sketch.base", "Base", 40.0, 30.0)
    features = [
        _extrusion("feature.base", "Base extrusion", 0, "sketch.base", (0, 0, 1), 16.0),
        _hole(
            "feature.hole",
            "Blind hole",
            1,
            (20, 15, 16),
            (0, 0, -1),
            10.0,
            depth=9.0,
            dependencies=["feature.base"],
        ),
    ]
    return _graph(spec, [sketch], features)


def _four_hole_plate(spec: SampleSpec) -> CADGraph:
    sketch = _xy_rectangle_sketch("sketch.base", "Base", 80.0, 50.0)
    features = [
        _extrusion("feature.base", "Base extrusion", 0, "sketch.base", (0, 0, 1), 8.0),
        _hole(
            "feature.hole.lower",
            "Lower seed hole",
            1,
            (12, 12, 8),
            (0, 0, -1),
            6.0,
            dependencies=["feature.base"],
        ),
        _hole(
            "feature.hole.upper",
            "Upper seed hole",
            2,
            (12, 38, 8),
            (0, 0, -1),
            6.0,
            dependencies=["feature.hole.lower"],
        ),
        _linear_pattern(
            "feature.pattern.lower",
            "Lower hole pattern",
            3,
            "feature.hole.lower",
            (1, 0, 0),
            2,
            56.0,
        ),
        _linear_pattern(
            "feature.pattern.upper",
            "Upper hole pattern",
            4,
            "feature.hole.upper",
            (1, 0, 0),
            2,
            56.0,
        ),
    ]
    return _graph(spec, [sketch], features)


def _pocketed_plate(spec: SampleSpec) -> CADGraph:
    base = _xy_rectangle_sketch("sketch.base", "Base", 90.0, 60.0)
    pocket = _xy_rectangle_sketch("sketch.pocket", "Pocket", 54.0, 30.0, x=18.0, y=15.0, z=10.0)
    features = [
        _extrusion("feature.base", "Base extrusion", 0, "sketch.base", (0, 0, 1), 10.0),
        _pocket("feature.pocket", "Central pocket", 1, "sketch.pocket", 5.0, ["feature.base"]),
    ]
    for index, (x, y) in enumerate(((10, 10), (80, 10), (10, 50), (80, 50)), start=1):
        prior = features[-1]["id"]
        features.append(
            _hole(
                f"feature.hole.{index}",
                f"Mounting hole {index}",
                index + 1,
                (x, y, 10),
                (0, 0, -1),
                6.0,
                dependencies=[prior],
            )
        )
    return _graph(spec, [base, pocket], features)


def _l_bracket(spec: SampleSpec) -> CADGraph:
    sketch = _sketch(
        "sketch.base",
        "L profile",
        origin=(0.0, 0.0, 0.0),
        normal=(1.0, 0.0, 0.0),
        x_axis=(0.0, 1.0, 0.0),
        entity=_polyline(
            "sketch.base.polyline",
            [(0, 0), (40, 0), (40, 6), (6, 6), (6, 45), (0, 45)],
        ),
    )
    features = [
        _extrusion("feature.base", "L bracket", 0, "sketch.base", (1, 0, 0), 60.0),
    ]
    holes = (
        ((15, 25, 6), (0, 0, -1), "Foot hole 1"),
        ((45, 25, 6), (0, 0, -1), "Foot hole 2"),
        ((15, 6, 27), (0, -1, 0), "Upright hole 1"),
        ((45, 6, 27), (0, -1, 0), "Upright hole 2"),
    )
    for index, (position, axis, name) in enumerate(holes, start=1):
        features.append(
            _hole(
                f"feature.hole.{index}",
                name,
                index,
                position,
                axis,
                8.0,
                dependencies=[features[-1]["id"]],
            )
        )
    return _graph(spec, [sketch], features)


def _flange(spec: SampleSpec) -> CADGraph:
    sketch = _xz_revolution_sketch(
        "sketch.base",
        "Flange profile",
        [(0, 0), (35, 0), (35, 8), (18, 8), (18, 20), (0, 20)],
    )
    features = [
        _revolution("feature.base", "Flange revolution", 0, "sketch.base"),
        _hole(
            "feature.bore",
            "Central bore",
            1,
            (0, 0, 20),
            (0, 0, -1),
            16.0,
            dependencies=["feature.base"],
        ),
        _hole(
            "feature.bolt",
            "Bolt seed hole",
            2,
            (27, 0, 8),
            (0, 0, -1),
            6.0,
            dependencies=["feature.bore"],
        ),
        _circular_pattern("feature.pattern", "Bolt circle", 3, "feature.bolt", 6, 360.0),
    ]
    return _graph(spec, [sketch], features)


def _spacer(spec: SampleSpec) -> CADGraph:
    sketch = _xy_circle_sketch("sketch.base", "Spacer profile", 12.0)
    features = [
        _extrusion("feature.base", "Spacer extrusion", 0, "sketch.base", (0, 0, 1), 18.0),
        _hole(
            "feature.bore",
            "Central bore",
            1,
            (0, 0, 18),
            (0, 0, -1),
            12.0,
            dependencies=["feature.base"],
        ),
    ]
    return _graph(spec, [sketch], features)


def _shaft_collar(spec: SampleSpec) -> CADGraph:
    sketch = _xy_circle_sketch("sketch.base", "Collar profile", 18.0)
    features = [
        _extrusion("feature.base", "Collar extrusion", 0, "sketch.base", (0, 0, 1), 16.0),
        _hole(
            "feature.bore",
            "Axial bore",
            1,
            (0, 0, 16),
            (0, 0, -1),
            18.0,
            dependencies=["feature.base"],
        ),
        _hole(
            "feature.radial",
            "Radial hole",
            2,
            (18, 0, 8),
            (-1, 0, 0),
            5.0,
            dependencies=["feature.bore"],
        ),
    ]
    return _graph(spec, [sketch], features)


def _stepped_part(spec: SampleSpec) -> CADGraph:
    sketch = _xz_revolution_sketch(
        "sketch.base",
        "Stepped profile",
        [(0, 0), (10, 0), (10, 25), (18, 25), (18, 37), (7, 37), (7, 55), (0, 55)],
    )
    features = [_revolution("feature.base", "Stepped revolution", 0, "sketch.base")]
    return _graph(spec, [sketch], features)


SAMPLE_SPECS: tuple[SampleSpec, ...] = (
    SampleSpec(
        "rectangular-block",
        "Rectangular block",
        1,
        (0, 0, 0, 40, 30, 12),
        14400.0,
        6,
        0,
        _rectangular_block,
    ),
    SampleSpec(
        "block-through-hole",
        "Block with through hole",
        2,
        (0, 0, 0, 40, 30, 12),
        13796.814210510760,
        6,
        1,
        _block_through_hole,
    ),
    SampleSpec(
        "block-blind-hole",
        "Block with blind hole",
        3,
        (0, 0, 0, 40, 30, 16),
        18493.141652942297,
        7,
        1,
        _block_blind_hole,
    ),
    SampleSpec(
        "four-hole-mounting-plate",
        "Four-hole mounting plate",
        4,
        (0, 0, 0, 80, 50, 8),
        31095.221315766132,
        6,
        4,
        _four_hole_plate,
    ),
    SampleSpec(
        "pocketed-mounting-plate",
        "Pocketed mounting plate",
        5,
        (0, 0, 0, 90, 60, 10),
        44769.026644707687,
        11,
        4,
        _pocketed_plate,
    ),
    SampleSpec(
        "l-bracket-with-holes",
        "L-bracket with mounting holes",
        6,
        (0, 0, 0, 60, 40, 45),
        27233.628421021516,
        8,
        4,
        _l_bracket,
        True,
    ),
    SampleSpec(
        "flange",
        "Flange",
        7,
        (-35, -35, 0, 35, 35, 20),
        37623.713619391347,
        3,
        9,
        _flange,
    ),
    SampleSpec(
        "spacer",
        "Spacer",
        8,
        (-12, -12, 0, 12, 12, 18),
        6107.256118578557,
        2,
        2,
        _spacer,
    ),
    SampleSpec(
        "shaft-collar",
        "Shaft collar",
        9,
        (-18, -18, 0, 18, 18, 16),
        11859.186850680926,
        2,
        4,
        _shaft_collar,
    ),
    SampleSpec(
        "stepped-turned-part",
        "Stepped turned part",
        10,
        (-18, -18, 0, 18, 18, 55),
        22839.378591597804,
        4,
        3,
        _stepped_part,
    ),
)


SAMPLES_BY_SLUG = {spec.slug: spec for spec in SAMPLE_SPECS}


def sample_spec(slug: str) -> SampleSpec:
    """Return a sample specification or raise a useful error."""

    try:
        return SAMPLES_BY_SLUG[slug]
    except KeyError as exc:
        choices = ", ".join(SAMPLES_BY_SLUG)
        raise KeyError(f"unknown sample {slug!r}; choose one of: {choices}") from exc


def sample_graph(slug: str) -> CADGraph:
    """Construct and strictly validate one deterministic sample CADGraph."""

    return sample_spec(slug).graph()


@dataclass(frozen=True, slots=True)
class GeneratedSample:
    """Stable summary of one generated sample artifact directory."""

    slug: str
    directory: str
    volume: float
    bbox: tuple[float, float, float, float, float, float]
    artifact_hashes: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "directory": self.directory,
            "volume": self.volume,
            "bbox": list(self.bbox),
            "artifactHashes": dict(self.artifact_hashes),
        }


def _compile_shape(graph: CADGraph) -> Any:
    from .compiler import compile_cadgraph

    result = compile_cadgraph(graph)
    if not result.success:
        details = "; ".join(error.kernel_error for error in result.errors)
        raise ValueError(f"sample {graph.id} failed to compile: {details}")
    return result.require_shape()


def _exact_bbox(shape: Any) -> tuple[float, float, float, float, float, float]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    native = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, native, False, False)
    return tuple(float(item) for item in native.Get())  # type: ignore[return-value]


def _assert_expected_geometry(spec: SampleSpec, shape: Any) -> dict[str, Any]:
    bbox = _exact_bbox(shape)
    volume = float(shape.Volume())
    if not np.allclose(bbox, spec.expected_bbox, rtol=0, atol=1e-6):
        raise ValueError(f"{spec.slug} bbox {bbox!r} != expected {spec.expected_bbox!r}")
    if not np.isclose(volume, spec.expected_volume, rtol=0, atol=1e-6):
        raise ValueError(
            f"{spec.slug} volume {volume:.12f} != expected {spec.expected_volume:.12f}"
        )
    kinds = [str(face.geomType()) for face in shape.Faces()]
    planar = kinds.count("PLANE")
    cylindrical = kinds.count("CYLINDER")
    if (planar, cylindrical) != (
        spec.expected_planar_faces,
        spec.expected_cylindrical_faces,
    ):
        raise ValueError(
            f"{spec.slug} face signature P/C={planar}/{cylindrical}, expected "
            f"{spec.expected_planar_faces}/{spec.expected_cylindrical_faces}"
        )
    return {
        "bbox": list(bbox),
        "volume": volume,
        "faceCount": len(shape.Faces()),
        "edgeCount": len(shape.Edges()),
        "planarFaceCount": planar,
        "cylindricalFaceCount": cylindrical,
    }


def _artifact_summary(artifact: Any) -> dict[str, Any]:
    return {
        "format": artifact.format,
        "byteSize": artifact.byte_size,
        "sha256": artifact.sha256,
        "vertexCount": artifact.vertex_count,
        "triangleCount": artifact.triangle_count,
        "linearTolerance": artifact.linear_tolerance,
        "angularTolerance": artifact.angular_tolerance,
    }


def _write_thumbnail(mesh: Any, destination: Path, title: str) -> None:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    projected = np.column_stack(
        (
            (vertices[:, 0] - vertices[:, 1]) * np.sqrt(3.0) / 2.0,
            (vertices[:, 0] + vertices[:, 1]) * 0.5 - vertices[:, 2],
        )
    )
    minimum = projected.min(axis=0)
    span = np.maximum(projected.max(axis=0) - minimum, 1e-12)
    scale = min(196.0 / span[0], 126.0 / span[1])
    offset = np.asarray((12.0, 22.0)) + ((196.0, 126.0) - span * scale) / 2.0
    screen = (projected - minimum) * scale + offset
    segments: set[tuple[float, float, float, float]] = set()
    for triangle in mesh.triangles:
        pairs = (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        )
        for first, second in pairs:
            a = tuple(float(round(item, 3)) for item in screen[first])
            b = tuple(float(round(item, 3)) for item in screen[second])
            start, end = sorted((a, b))
            segments.add((start[0], start[1], end[0], end[1]))
    path_data = " ".join(
        f"M{x1:.3f},{y1:.3f}L{x2:.3f},{y2:.3f}" for x1, y1, x2, y2 in sorted(segments)
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 160" '
        'role="img" aria-labelledby="title">\n'
        f'  <title id="title">{title}</title>\n'
        '  <rect width="220" height="160" fill="#0b0f14"/>\n'
        '  <path d="' + path_data + '" fill="none" stroke="#4da3ff" stroke-width="0.65" '
        'stroke-linecap="round" stroke-linejoin="round"/>\n'
        '  <rect x="0.5" y="0.5" width="219" height="159" fill="none" '
        'stroke="#2a3441"/>\n'
        "</svg>\n"
    )
    destination.write_text(svg, encoding="utf-8", newline="\n")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_sample(spec: SampleSpec, output_root: str | Path) -> GeneratedSample:
    """Compile, validate and write every deterministic artifact for one sample."""

    from .source import write_cadquery_source
    from .tessellation import (
        tessellate_shape,
        transform_tessellation,
        write_binary_stl,
        write_glb,
        write_obj,
    )
    from .validation import export_step_validated

    destination = Path(output_root) / spec.slug
    destination.mkdir(parents=True, exist_ok=True)
    graph = spec.graph()
    baseline_shape = _compile_shape(graph)
    actual = _assert_expected_geometry(spec, baseline_shape)

    high_tessellation = tessellate_shape(
        baseline_shape,
        linear_tolerance=0.025,
        angular_tolerance=0.10,
    )
    high = write_binary_stl(
        high_tessellation,
        destination / "source-high.stl",
        linear_tolerance=0.025,
        angular_tolerance=0.10,
    )
    low_tessellation = tessellate_shape(
        baseline_shape,
        linear_tolerance=0.20,
        angular_tolerance=0.30,
    )
    low = write_binary_stl(
        low_tessellation,
        destination / "source-low.stl",
        linear_tolerance=0.20,
        angular_tolerance=0.30,
    )
    transform = sample_transform(spec)
    rotation = np.asarray(transform.rotation, dtype=np.float64)
    translation = np.asarray(transform.translation_mm, dtype=np.float64)

    def transform_vertex(vertex: tuple[float, float, float]) -> tuple[float, float, float]:
        result = rotation @ np.asarray(vertex, dtype=np.float64) + translation
        return float(result[0]), float(result[1]), float(result[2])

    random_tessellation = transform_tessellation(
        high_tessellation,
        transform_vertex,
    )
    random_mesh = write_binary_stl(
        random_tessellation,
        destination / "source-random.stl",
        linear_tolerance=0.025,
        angular_tolerance=0.10,
    )
    model_tessellation = tessellate_shape(
        baseline_shape,
        linear_tolerance=0.10,
        angular_tolerance=0.20,
    )
    glb = write_glb(
        model_tessellation,
        destination / "model.glb",
        linear_tolerance=0.10,
        angular_tolerance=0.20,
    )
    model_stl = write_binary_stl(
        model_tessellation,
        destination / "model.stl",
        linear_tolerance=0.10,
        angular_tolerance=0.20,
    )
    model_obj = write_obj(
        model_tessellation,
        destination / "model.obj",
        linear_tolerance=0.10,
        angular_tolerance=0.20,
    )
    step = export_step_validated(
        baseline_shape,
        destination / "model.step",
        units="mm",
        linear_resolution=max(graph.project_tolerance.linear_resolution, 0.025),
        angular_tolerance=np.radians(graph.project_tolerance.angular_deviation_deg),
    )

    document = graph.model_dump(mode="json", by_alias=True)
    document["source"] = {
        "format": "generated",
        "sha256": high.sha256,
        "originalFileName": "source-high.stl",
        "byteSize": high.byte_size,
        "triangleCount": high.triangle_count,
        "declaredUnits": "mm",
        "scaleFactor": 1.0,
    }
    document["validation"] = {
        "status": "valid",
        "brepValid": True,
        "stepReimportValid": True,
        "toleranceSatisfied": True,
        "checkedAt": FIXED_TIMESTAMP,
        "lastValidFeatureId": graph.features[-1].id,
        "issues": [],
    }
    final_graph = CADGraph.model_validate(document)
    cadgraph_path = destination / "model.cadgraph.json"
    cadgraph_path.write_text(canonical_json(final_graph), encoding="utf-8", newline="\n")
    write_cadquery_source(final_graph, destination / "model.cq.py")

    thumbnail_path = destination / "thumbnail.svg"
    _write_thumbnail(low_tessellation, thumbnail_path, spec.name)

    metadata = {
        "schemaVersion": 1,
        "slug": spec.slug,
        "name": spec.name,
        "seed": spec.seed,
        "featureIds": [feature.id for feature in final_graph.features],
        "expected": {
            "bbox": list(spec.expected_bbox),
            "volume": spec.expected_volume,
            "planarFaceCount": spec.expected_planar_faces,
            "cylindricalFaceCount": spec.expected_cylindrical_faces,
        },
        "actual": actual,
        "randomTransform": {
            "anglesDeg": list(transform.angles_deg),
            "translationMm": list(transform.translation_mm),
            "rotation": [list(row) for row in transform.rotation],
        },
        "meshes": {
            "high": _artifact_summary(high),
            "low": _artifact_summary(low),
            "random": _artifact_summary(random_mesh),
            "glb": _artifact_summary(glb),
            "stl": _artifact_summary(model_stl),
            "obj": _artifact_summary(model_obj),
        },
        "step": {
            "sha256": step.sha256,
            "volumeDelta": step.volume_delta,
            "volumeTolerance": step.volume_tolerance,
            "topologyCountsMatch": step.topology_counts_match,
            "sourceValid": step.source.valid,
            "reimportValid": step.reimport.valid,
        },
    }
    metadata_path = destination / "metadata.json"
    metadata_path.write_text(canonical_json(metadata), encoding="utf-8", newline="\n")

    artifact_paths = sorted(
        path for path in destination.iterdir() if path.is_file() and path.name != "manifest.json"
    )
    manifest = {
        "schemaVersion": 1,
        "sample": spec.slug,
        "generatedAt": FIXED_TIMESTAMP,
        "artifacts": [
            {
                "name": path.name,
                "byteSize": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            for path in artifact_paths
        ],
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8", newline="\n")
    hashes = tuple(
        (path.name, _sha256_file(path))
        for path in sorted((*artifact_paths, manifest_path), key=lambda item: item.name)
    )
    return GeneratedSample(
        spec.slug,
        str(destination),
        actual["volume"],
        _exact_bbox(baseline_shape),
        hashes,
    )


def generate_sample_corpus(
    output_root: str | Path = "samples/generated",
    slugs: list[str] | tuple[str, ...] | None = None,
) -> tuple[GeneratedSample, ...]:
    """Generate the full corpus, or an explicitly selected stable subset."""

    selected = SAMPLE_SPECS if slugs is None else tuple(sample_spec(slug) for slug in slugs)
    return tuple(generate_sample(spec, output_root) for spec in selected)


__all__ = [
    "FIXED_TIMESTAMP",
    "SAMPLES_BY_SLUG",
    "SAMPLE_SEED_BASE",
    "SAMPLE_SPECS",
    "GeneratedSample",
    "SampleSpec",
    "SampleTransform",
    "generate_sample",
    "generate_sample_corpus",
    "sample_graph",
    "sample_spec",
    "sample_transform",
]
