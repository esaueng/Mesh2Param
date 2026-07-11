"""Explicit, deterministic migrations into the current CADGraph schema."""

from __future__ import annotations

from copy import deepcopy
from typing import cast

from pydantic import JsonValue, ValidationError

from .models import CADGraph, CURRENT_SCHEMA_VERSION


LEGACY_SCHEMA_VERSION = "0.1.0"


class MigrationError(ValueError):
    """Raised when a CADGraph version cannot be migrated safely."""


_DEFAULT_SCORE_WEIGHTS: dict[str, float] = {
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
}


def _require_object(value: object, label: str = "CADGraph") -> dict[str, JsonValue]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise MigrationError(f"{label} must be a JSON object")
    return cast(dict[str, JsonValue], deepcopy(value))


def _normalize_entities(sketch: dict[str, JsonValue]) -> None:
    entities = sketch.get("entities", [])
    if not isinstance(entities, list):
        return
    construction_kinds = {"constructionPoint", "constructionLine", "constructionAxis"}
    for raw_entity in entities:
        if not isinstance(raw_entity, dict):
            continue
        entity = cast(dict[str, JsonValue], raw_entity)
        if "kind" not in entity and isinstance(entity.get("type"), str):
            entity["kind"] = entity.pop("type")
        kind = entity.get("kind")
        if isinstance(kind, str):
            entity.setdefault("construction", kind in construction_kinds)
        entity.setdefault("sourceEvidence", [])
        entity.setdefault("confidence", 1.0)
        entity.setdefault("locked", False)
        entity.setdefault("suppressed", False)


def _normalize_feature(feature: dict[str, JsonValue], index: int) -> None:
    legacy_operation = feature.pop("type", None)
    if "operation" not in feature and isinstance(legacy_operation, str):
        operation_map: dict[str, tuple[str, str | None]] = {
            "baseExtrusion": ("extrusion", "base"),
            "additiveExtrusion": ("extrusion", "additive"),
            "subtractiveExtrusion": ("extrusion", "subtractive"),
            "throughHole": ("hole", "subtractive"),
            "blindHole": ("hole", "subtractive"),
            "baseRevolution": ("revolution", "base"),
            "additiveRevolution": ("revolution", "additive"),
            "subtractiveRevolution": ("revolution", "subtractive"),
        }
        operation, boolean_mode = operation_map.get(legacy_operation, (legacy_operation, None))
        feature["operation"] = operation
        if boolean_mode is not None:
            feature.setdefault("booleanMode", boolean_mode)
        if legacy_operation == "throughHole":
            feature.setdefault("holeType", "through")
        elif legacy_operation == "blindHole":
            feature.setdefault("holeType", "blind")
    if "dependencies" not in feature and isinstance(feature.get("dependsOn"), list):
        feature["dependencies"] = feature.pop("dependsOn")
    feature.setdefault("order", index)
    feature.setdefault("dependencies", [])
    feature.setdefault("suppressed", False)
    feature.setdefault("sourceEvidence", [])
    feature.setdefault("confidence", 1.0)
    feature.setdefault("userLocks", [])
    feature.setdefault("overrides", [])
    feature.setdefault("semanticOutputs", [])


def _migrate_0_1_0(document: dict[str, JsonValue]) -> dict[str, JsonValue]:
    document["schemaVersion"] = CURRENT_SCHEMA_VERSION
    if "features" not in document and isinstance(document.get("operations"), list):
        document["features"] = document.pop("operations")
    if "deterministicSeed" not in document and isinstance(document.get("randomSeed"), int):
        document["deterministicSeed"] = document.pop("randomSeed")

    sketches = document.setdefault("sketches", [])
    if isinstance(sketches, list):
        for raw_sketch in sketches:
            if not isinstance(raw_sketch, dict):
                continue
            sketch = cast(dict[str, JsonValue], raw_sketch)
            _normalize_entities(sketch)
            sketch.setdefault("constraints", [])
            sketch.setdefault("profiles", [])
            sketch.setdefault("sourceEvidence", [])
            sketch.setdefault("confidence", 1.0)
            sketch.setdefault("userLocks", [])
            sketch.setdefault("overrides", [])
            sketch.setdefault("suppressed", False)

    features = document.setdefault("features", [])
    if isinstance(features, list):
        for index, raw_feature in enumerate(features):
            if isinstance(raw_feature, dict):
                _normalize_feature(cast(dict[str, JsonValue], raw_feature), index)

    legacy_tolerance = document.pop("tolerance", None)
    surface_tolerance = float(legacy_tolerance) if isinstance(legacy_tolerance, (int, float)) else 0.1
    document.setdefault(
        "sourceCoordinateFrame",
        {
            "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
            "xAxis": {"x": 1.0, "y": 0.0, "z": 0.0},
            "yAxis": {"x": 0.0, "y": 1.0, "z": 0.0},
            "zAxis": {"x": 0.0, "y": 0.0, "z": 1.0},
            "locked": False,
            "confidence": 0.0,
            "evidenceIds": [],
        },
    )
    document.setdefault(
        "projectTolerance",
        {
            "surfaceDeviation": surface_tolerance,
            "angularDeviationDeg": 1.0,
            "linearResolution": max(surface_tolerance / 10.0, 1e-9),
        },
    )
    document.setdefault("semanticTopology", [])
    document.setdefault("sourceEvidence", [])
    document.setdefault("userLocks", [])
    document.setdefault("overrides", [])
    document.setdefault(
        "reconstructionSettings",
        {
            "maxFeatures": 64,
            "beamWidth": 3,
            "candidatesPerResidual": 4,
            "wallClockSeconds": 300.0,
            "maxRebuilds": 200,
            "minScoreImprovement": 0.001,
            "nominalSnappingEnabled": True,
            "nominalSnapTolerance": surface_tolerance,
            "scoreWeights": deepcopy(_DEFAULT_SCORE_WEIGHTS),
        },
    )
    document.setdefault(
        "engineVersions",
        {
            "mesh2param": "unknown",
            "contracts": CURRENT_SCHEMA_VERSION,
            "cadBackend": "OCCT",
            "cadQuery": "unknown",
            "ocp": "unknown",
            "dependencies": {},
        },
    )
    document.setdefault("deterministicSeed", 0)
    document.setdefault(
        "fitMetrics",
        {
            "rmsSurfaceDistance": 0.0,
            "p95SurfaceDistance": 0.0,
            "maxSurfaceDistance": 0.0,
            "normalAgreement": 0.0,
            "volumeDifference": 0.0,
            "overlap": 0.0,
            "unmatchedSourceArea": 0.0,
            "excessResultArea": 0.0,
            "score": 0.0,
        },
    )
    document.setdefault(
        "validation",
        {
            "status": "notRun",
            "brepValid": None,
            "stepReimportValid": None,
            "toleranceSatisfied": None,
            "issues": [],
        },
    )
    document.setdefault(
        "versionMetadata",
        {
            "versionId": "version.migrated",
            "createdAt": "1970-01-01T00:00:00Z",
            "createdBy": "migration",
            "message": "Migrated from CADGraph 0.1.0",
        },
    )
    return document


def migrate_document(value: object) -> dict[str, JsonValue]:
    """Migrate a JSON-like object and return a detached current-version document.

    Migration never invents missing feature geometry. Legacy field names and
    safe metadata defaults are normalized, then strict validation reports any
    information that still requires the user or reconstruction engine.
    """

    document = _require_object(value)
    version = document.get("schemaVersion")
    if version == CURRENT_SCHEMA_VERSION:
        return document
    if version == LEGACY_SCHEMA_VERSION:
        return _migrate_0_1_0(document)
    raise MigrationError(f"unsupported CADGraph schemaVersion: {version!r}")


def migrate_cadgraph(value: object) -> CADGraph:
    """Migrate and strictly validate a CADGraph document."""

    try:
        return CADGraph.model_validate(migrate_document(value), strict=False)
    except ValidationError as error:
        raise MigrationError(f"migrated CADGraph is invalid: {error}") from error


__all__ = ["LEGACY_SCHEMA_VERSION", "MigrationError", "migrate_cadgraph", "migrate_document"]
