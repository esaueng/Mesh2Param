"""Mesh2Param CADGraph contracts."""

from .migrations import LEGACY_SCHEMA_VERSION, MigrationError, migrate_cadgraph, migrate_document
from .models import CADGraph, CURRENT_SCHEMA_VERSION, Feature, SketchEntity
from .schema import load_schema, schema_path
from .serialization import SerializationError, canonical_json, canonical_json_bytes, content_sha256

__all__ = [
    "CADGraph",
    "CURRENT_SCHEMA_VERSION",
    "Feature",
    "LEGACY_SCHEMA_VERSION",
    "MigrationError",
    "SerializationError",
    "SketchEntity",
    "canonical_json",
    "canonical_json_bytes",
    "content_sha256",
    "load_schema",
    "migrate_cadgraph",
    "migrate_document",
    "schema_path",
]
