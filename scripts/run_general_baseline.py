"""Record the explicit faceted baseline for the general-parametric corpus."""

from __future__ import annotations

import argparse
import json
import platform
import tempfile
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from importlib import metadata
from pathlib import Path
from typing import Any

import trimesh
from mesh2param.comparison import ComparisonSettings, compare_mesh_to_step
from mesh2param.faceted import FacetedFallbackError, create_faceted_fallback
from mesh2param.general_fixtures import (
    CORPUS_MANIFEST_NAME,
    FIXTURE_MANIFEST_NAME,
    FIXTURE_STL_NAME,
)


def _fixture_baseline(directory: Path, sample_count: int) -> dict[str, Any]:
    manifest = json.loads((directory / FIXTURE_MANIFEST_NAME).read_text(encoding="utf-8"))
    stl_path = directory / FIXTURE_STL_NAME
    units = manifest["units"]
    source_triangles = int(manifest["stl"]["triangleCount"])
    record: dict[str, Any] = {
        "slug": manifest["slug"],
        "category": manifest["category"],
        "expectation": manifest["expectation"],
        "units": units,
        "sourceTriangleCount": source_triangles,
        "sourceStlByteSize": manifest["stl"]["byteSize"],
        "sourceStlSha256": manifest["stl"]["sha256"],
    }
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="mesh2param-general-baseline-") as scratch:
            result = create_faceted_fallback(stl_path, scratch, units=units)
            elapsed = time.perf_counter() - started
            step_path = Path(result.step.path)
            source_mesh = trimesh.load_mesh(stl_path, file_type="stl", process=True)
            if not isinstance(source_mesh, trimesh.Trimesh):
                raise ValueError("general baseline fixture did not load as one mesh")
            comparison = compare_mesh_to_step(
                source_mesh,
                step_path,
                units=units,
                settings=ComparisonSettings(sample_count_each_direction=sample_count),
            )
            record.update(
                {
                    "status": "converted",
                    "runtimeSeconds": elapsed,
                    "facetedFaceCount": result.step.source.face_count,
                    "facetedEdgeCount": result.step.source.edge_count,
                    "stepByteSize": step_path.stat().st_size,
                    "stepSha256": result.step.sha256,
                    "facesPerSourceTriangle": (
                        result.step.source.face_count / max(source_triangles, 1)
                    ),
                    "comparison": comparison.to_dict(),
                }
            )
    except (FacetedFallbackError, ValueError) as exc:
        record.update(
            {
                "status": "error",
                "runtimeSeconds": time.perf_counter() - started,
                "error": {
                    "type": type(exc).__name__,
                    "phase": getattr(exc, "phase", None),
                    "code": getattr(exc, "code", None),
                    "message": str(exc),
                },
            }
        )
    return record


def run_baseline(
    fixture_root: Path,
    output_path: Path,
    sample_count: int,
    workers: int = 1,
) -> dict[str, Any]:
    if sample_count < 1:
        raise ValueError("baseline sample count must be positive")
    if workers < 1:
        raise ValueError("baseline worker count must be positive")
    corpus = json.loads((fixture_root / CORPUS_MANIFEST_NAME).read_text(encoding="utf-8"))
    directories = [fixture_root / entry["slug"] for entry in corpus["fixtures"]]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            fixtures = list(
                executor.map(_fixture_baseline, directories, [sample_count] * len(directories))
            )
    else:
        fixtures = [_fixture_baseline(directory, sample_count) for directory in directories]
    baseline = {
        "scope": "explicit faceted baseline for general-parametric reconstruction (G2a)",
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "machine": platform.machine(),
        },
        "packages": {
            name: metadata.version(name) for name in ("cadquery", "cadquery-ocp", "trimesh")
        },
        "comparisonSampleCountEachDirection": sample_count,
        "fixtures": fixtures,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return baseline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("samples/general-parametric-benchmark"),
        help="fixture corpus root (default: samples/general-parametric-benchmark)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/general-baseline/baseline.json"),
        help="baseline report path (default: artifacts/general-baseline/baseline.json)",
    )
    parser.add_argument(
        "--sample-count",
        type=int,
        default=1000,
        help="comparison samples in each direction (default: 1000)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="fixture-level process parallelism; output order follows the manifest",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    baseline = run_baseline(args.fixtures, args.output, args.sample_count, args.workers)
    print(json.dumps(baseline, indent=2, sort_keys=True))
    return 0 if all(row["status"] == "converted" for row in baseline["fixtures"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main", "run_baseline"]
