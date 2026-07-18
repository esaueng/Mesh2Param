"""Content-addressed cache for curved surface fits (Milestone 4).

A fit is cached by everything that determines it: the source mesh content
hash, the full reconstruction settings, the freeform chart's exact triangle
evidence, and the fit algorithm version. Hits skip only the expensive fitting
stage; assembly and every validation gate re-run on the rebuilt network, so a
cached result is byte-identical to a fresh one and never bypasses a gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

# Bump whenever fitting, parameterization, or assembly changes geometry.
FIT_CACHE_ALGORITHM = "mesh2param/curved-fit/4"


def mesh_content_sha256(mesh: trimesh.Trimesh) -> str:
    """Deterministic content hash of a triangle mesh's geometry."""

    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(mesh.vertices, dtype=np.float64).tobytes())
    digest.update(np.ascontiguousarray(mesh.faces, dtype=np.int64).tobytes())
    return digest.hexdigest()


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class CurvedFitCache:
    """A directory of canonical JSON fit payloads keyed by evidence hash."""

    directory: Path

    def key(
        self,
        source_sha256: str,
        settings: Any,
        network_settings: Any,
        chart_arrays: tuple[np.ndarray, np.ndarray],
        extras: dict[str, Any] | None = None,
    ) -> str:
        chart_vertices, chart_faces = chart_arrays
        chart_digest = hashlib.sha256()
        chart_digest.update(np.ascontiguousarray(chart_vertices, dtype=np.float64).tobytes())
        chart_digest.update(np.ascontiguousarray(chart_faces, dtype=np.int64).tobytes())
        payload = {
            "algorithm": FIT_CACHE_ALGORITHM,
            "sourceSha256": source_sha256,
            "settings": asdict(settings),
            "networkSettings": asdict(network_settings),
            "chartSha256": chart_digest.hexdigest(),
        }
        # Only present when set, so keys without extras stay stable.
        if extras:
            payload["extras"] = extras
        return hashlib.sha256(_canonical_bytes(payload)).hexdigest()

    def _path(self, key: str) -> Path:
        if not key or any(character not in "0123456789abcdef" for character in key):
            raise ValueError("cache keys are lowercase hex digests")
        return Path(self.directory) / f"{key}.json"

    def load(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.is_file():
            return None
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return None
        return loaded

    def store(self, key: str, payload: dict[str, Any]) -> Path:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(_canonical_bytes(payload))
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return path


__all__ = ["FIT_CACHE_ALGORITHM", "CurvedFitCache", "mesh_content_sha256"]
