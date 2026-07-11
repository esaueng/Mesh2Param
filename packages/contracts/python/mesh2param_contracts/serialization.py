"""Deterministic CADGraph serialization helpers."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import TypeAlias

from pydantic import BaseModel


CanonicalValue: TypeAlias = None | bool | int | float | str | list["CanonicalValue"] | dict[str, "CanonicalValue"]


class SerializationError(ValueError):
    """Raised when a value cannot be represented by deterministic JSON."""


def _normalize(value: object) -> CanonicalValue:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SerializationError("NaN and infinite values are not valid CADGraph JSON")
        if value == 0.0:
            return 0
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, CanonicalValue] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise SerializationError("CADGraph object keys must be strings")
            normalized[key] = _normalize(value[key])
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        return [_normalize(item) for item in value]
    raise SerializationError(f"unsupported CADGraph JSON value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Return canonical UTF-8 JSON text with a single trailing newline.

    Object keys are sorted recursively, insignificant whitespace is removed,
    negative zero is normalized and non-finite values are rejected. Arrays
    retain their authored order because feature and topology ordering is
    semantically meaningful.
    """

    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"


def canonical_json_bytes(value: object) -> bytes:
    """Return :func:`canonical_json` encoded as UTF-8."""

    return canonical_json(value).encode("utf-8")


def content_sha256(value: object) -> str:
    """Hash the canonical serialized representation."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


__all__ = [
    "SerializationError",
    "canonical_json",
    "canonical_json_bytes",
    "content_sha256",
]
