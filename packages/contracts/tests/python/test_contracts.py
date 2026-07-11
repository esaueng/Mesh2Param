from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from mesh2param_contracts import CADGraph, canonical_json, content_sha256, load_schema, migrate_cadgraph


FIXTURE = Path(__file__).parents[1] / "fixtures" / "base.cadgraph.json"


def fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_schema_and_strict_model_accept_fixture() -> None:
    document = fixture()
    Draft202012Validator(load_schema(), format_checker=FormatChecker()).validate(document)
    graph = CADGraph.model_validate_json(json.dumps(document))
    assert graph.schema_version == "1.0.0"
    assert {entity.kind for entity in graph.sketches[0].entities} == {
        "point", "constructionPoint", "line", "constructionLine", "polyline",
        "rectangle", "circle", "circularArc", "closedProfile", "constructionAxis",
    }


def test_unknown_fields_are_rejected() -> None:
    document = fixture()
    document["unexpected"] = True
    with pytest.raises(ValidationError):
        CADGraph.model_validate_json(json.dumps(document))


def test_reference_integrity_is_enforced() -> None:
    document = fixture()
    document["features"][0]["dependencies"] = ["feature.missing"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="unknown references"):
        CADGraph.model_validate_json(json.dumps(document))


def test_serialization_is_deterministic() -> None:
    graph = CADGraph.model_validate_json(json.dumps(fixture()))
    assert canonical_json(graph) == canonical_json(graph)
    assert len(content_sha256(graph)) == 64


def test_migration_is_deterministic_and_non_mutating() -> None:
    legacy = {
        "schemaVersion": "0.1.0", "id": "project.legacy", "name": "Legacy",
        "units": "mm", "operations": [], "tolerance": 0.05, "randomSeed": 7,
    }
    original = deepcopy(legacy)
    migrated = migrate_cadgraph(legacy)
    assert migrated.schema_version == "1.0.0"
    assert migrated.deterministic_seed == 7
    assert legacy == original
