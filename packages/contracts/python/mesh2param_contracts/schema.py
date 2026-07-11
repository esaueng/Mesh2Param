"""Access to the authoritative CADGraph JSON Schema."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import cast

from pydantic import JsonValue


SCHEMA_FILE_NAME = "cadgraph.schema.json"


def schema_path() -> Path:
    """Locate the source-tree or wheel-packaged schema."""

    packaged = resources.files(__package__).joinpath("schema", SCHEMA_FILE_NAME)
    if packaged.is_file():
        return Path(str(packaged))
    source_tree = Path(__file__).resolve().parents[2] / "schema" / SCHEMA_FILE_NAME
    if source_tree.is_file():
        return source_tree
    raise FileNotFoundError(f"unable to locate {SCHEMA_FILE_NAME}")


def load_schema() -> dict[str, JsonValue]:
    """Load a detached copy of the authoritative JSON Schema."""

    with schema_path().open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    return cast(dict[str, JsonValue], value)


__all__ = ["SCHEMA_FILE_NAME", "load_schema", "schema_path"]
