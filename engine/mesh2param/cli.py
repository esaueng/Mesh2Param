"""Headless Mesh2Param compiler and bounded reconstruction CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mesh2param_contracts import CADGraph, canonical_json_bytes, migrate_cadgraph

from . import __version__
from .comparison import compare_mesh_to_step, write_residual_heatmap_glb
from .compiler import compile_cadgraph
from .ingest import ingest_mesh
from .reconstruction import ReconstructionError, reconstruct_file
from .repair import repair_mesh
from .samples import SAMPLES_BY_SLUG, generate_sample_corpus
from .segmentation import segment_mesh
from .selection import write_patch_selection_artifacts
from .source import write_cadquery_source
from .tessellation import Tessellation, export_glb, write_binary_stl
from .validation import export_step_validated, validate_step_file

UNITS = ("mm", "cm", "m", "in", "ft")


def _artifact_mapping(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        identifier, separator, raw_path = value.partition("=")
        if not separator or not identifier or not raw_path:
            raise argparse.ArgumentTypeError("artifacts must use ID=PATH")
        result[identifier] = Path(raw_path)
    return result


def _load_graph(path: Path) -> CADGraph:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("CADGraph root must be a JSON object")
    return migrate_cadgraph(document)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _print(value: Any, *, error: bool = False) -> None:
    print(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False),
        file=sys.stderr if error else sys.stdout,
    )


def _mesh_tessellation(mesh: Any) -> Tessellation:
    vertices = tuple(tuple(float(value) for value in vertex) for vertex in mesh.vertices)
    triangles = tuple(tuple(int(value) for value in face) for face in mesh.faces)
    return Tessellation(vertices, triangles, ())  # type: ignore[arg-type]


def _rebuild_command(args: argparse.Namespace) -> int:
    graph = _load_graph(args.input)
    artifacts = _artifact_mapping(args.artifact)
    result = compile_cadgraph(graph, artifact_resolver=artifacts)
    if not result.success:
        _print(result.to_dict(), error=True)
        return 2
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    shape = result.require_shape()
    step = export_step_validated(
        shape,
        output / "model.step",
        units=graph.units,
        linear_resolution=max(graph.project_tolerance.linear_resolution, 0.025),
    )
    glb = export_glb(shape, output / "model.glb")
    write_cadquery_source(graph, output / "model.cq.py", artifact_paths=artifacts)
    (output / "model.cadgraph.json").write_bytes(canonical_json_bytes(graph))
    report = result.to_dict()
    report["artifacts"] = {
        "step": step.to_dict(),
        "glb": {
            "path": glb.path,
            "byteSize": glb.byte_size,
            "sha256": glb.sha256,
            "vertexCount": glb.vertex_count,
            "triangleCount": glb.triangle_count,
        },
    }
    _write_json(output / "rebuild.json", report)
    _print(report)
    return 0


def _analyze_command(args: argparse.Namespace) -> int:
    source = ingest_mesh(args.source)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    report = {"units": args.units, **source.to_dict()}
    _write_json(output / "analysis.json", report)
    _print(report)
    return 0


def _repair_command(args: argparse.Namespace) -> int:
    source = ingest_mesh(args.source)
    result = repair_mesh(source)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    write_binary_stl(_mesh_tessellation(result.mesh), output / "repaired.stl")
    report = {"units": args.units, **result.to_dict()}
    _write_json(output / "repair.json", report)
    _print(report)
    return 0


def _segment_command(args: argparse.Namespace) -> int:
    source = ingest_mesh(args.source)
    repaired = repair_mesh(source)
    segmentation = segment_mesh(repaired.mesh)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    selection = write_patch_selection_artifacts(
        repaired.mesh,
        segmentation.patches,
        output / "patches.glb",
        output / "selection-map.json",
    )
    report = {
        "units": args.units,
        "repair": repaired.to_dict(),
        "segmentation": segmentation.to_dict(),
        "patchSelection": selection.to_dict(),
    }
    _write_json(output / "segment.json", report)
    _print(report)
    return 0


def _reconstruct_command(args: argparse.Namespace) -> int:
    result = reconstruct_file(args.source, args.output, units=args.units)
    _print(result.to_dict())
    return 0


def _compare_command(args: argparse.Namespace) -> int:
    source = ingest_mesh(args.source)
    repaired = repair_mesh(source)
    report = compare_mesh_to_step(repaired.mesh, args.model, units=args.units)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    heatmap = write_residual_heatmap_glb(
        repaired.mesh,
        report.source_vertex_residuals_mm,
        output / "residual-heatmap.glb",
        tolerance_mm=report.tolerance_mm,
    )
    payload = {"comparison": report.to_dict(), "residualHeatmap": heatmap.to_dict()}
    _write_json(output / "comparison.json", payload)
    _print(payload)
    return 0


def _validate_step_command(args: argparse.Namespace) -> int:
    report = validate_step_file(args.path, units=args.units)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "validation.json", report.to_dict())
    _print(report.to_dict())
    return 0 if report.valid else 2


def _samples_command(args: argparse.Namespace) -> int:
    if args.samples_action == "list":
        for spec in SAMPLES_BY_SLUG.values():
            print(f"{spec.slug}\t{spec.name}")
        return 0
    generated = generate_sample_corpus(args.output, args.samples)
    _print([item.to_dict() for item in generated])
    return 0


def _serve_command(_args: argparse.Namespace) -> int:
    print(
        "mesh2param: serve is unavailable until the M3 API service is installed; "
        "no server was started",
        file=sys.stderr,
    )
    return 2


def _mesh_input(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", type=Path)
    parser.add_argument("--units", choices=UNITS, default="mm")
    parser.add_argument("--output", type=Path, default=Path("artifacts"))


def _rebuild_parser(subparsers: Any, name: str) -> None:
    parser = subparsers.add_parser(
        name,
        help="rebuild a trusted CADGraph artifact bundle",
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="ID=PATH",
        help="resolve a trusted imported feature artifact; repeat as needed",
    )
    parser.set_defaults(handler=_rebuild_command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mesh2param",
        description=(
            "Analyze meshes, reconstruct the bounded supported scope, and rebuild CADGraph."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    for name, help_text, handler in (
        ("analyze", "inspect one STL/OBJ/PLY source", _analyze_command),
        ("repair", "apply explicit non-destructive mesh repair", _repair_command),
        ("segment", "fit deterministic plane/cylinder patches", _segment_command),
        ("reconstruct", "reconstruct the bounded L-bracket scope", _reconstruct_command),
    ):
        command = subparsers.add_parser(name, help=help_text)
        _mesh_input(command)
        command.set_defaults(handler=handler)

    _rebuild_parser(subparsers, "rebuild")

    compare_parser = subparsers.add_parser("compare", help="compare source mesh to STEP")
    compare_parser.add_argument("source", type=Path)
    compare_parser.add_argument("model", type=Path)
    compare_parser.add_argument("--units", choices=UNITS, default="mm")
    compare_parser.add_argument("--output", type=Path, default=Path("artifacts"))
    compare_parser.set_defaults(handler=_compare_command)

    validate_parser = subparsers.add_parser("validate", help="validate one STEP solid")
    validate_parser.add_argument("path", type=Path)
    validate_parser.add_argument("--units", choices=UNITS, default="mm")
    validate_parser.add_argument("--output", type=Path, default=Path("artifacts"))
    validate_parser.set_defaults(handler=_validate_step_command)
    samples_parser = subparsers.add_parser("samples", help="list or generate procedural samples")
    sample_subparsers = samples_parser.add_subparsers(dest="samples_action", required=True)
    list_parser = sample_subparsers.add_parser("list", help="list procedural samples")
    list_parser.set_defaults(handler=_samples_command)
    generate_parser = sample_subparsers.add_parser("generate", help="generate sample artifacts")
    generate_parser.add_argument("--output", type=Path, default=Path("samples/generated"))
    generate_parser.add_argument(
        "--sample", action="append", choices=tuple(SAMPLES_BY_SLUG), dest="samples"
    )
    generate_parser.set_defaults(handler=_samples_command)

    serve_parser = subparsers.add_parser("serve", help="start the M3 API service when installed")
    serve_parser.set_defaults(handler=_serve_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    normalized = list(sys.argv[1:] if argv is None else argv)
    if normalized[:1] == ["--"]:
        normalized = normalized[1:]
    args = parser.parse_args(normalized)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    try:
        return int(handler(args))
    except ReconstructionError as exc:
        _print({"status": "partial", "error": exc.to_dict()}, error=True)
        return 2
    except (OSError, ValueError, KeyError, argparse.ArgumentTypeError) as exc:
        print(f"mesh2param: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__: list[str] = ["build_parser", "main"]
