"""Command-line interface for the headless Mesh2Param M1 engine."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from mesh2param_contracts import CADGraph, migrate_cadgraph

from . import __version__
from .compiler import compile_cadgraph
from .samples import SAMPLES_BY_SLUG, generate_sample_corpus
from .source import write_cadquery_source
from .tessellation import export_glb
from .validation import export_step_validated, validate_step_file


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


def _compile_command(args: argparse.Namespace) -> int:
    graph = _load_graph(args.input)
    artifacts = _artifact_mapping(args.artifact)
    result = compile_cadgraph(graph, artifact_resolver=artifacts)
    if not result.success:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True), file=sys.stderr)
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
    report = result.to_dict()
    report["artifacts"] = {
        "step": step.to_dict(),
        "glb": glb.to_dict(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _validate_step_command(args: argparse.Namespace) -> int:
    report = validate_step_file(args.path, units=args.units)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.valid else 2


def _samples_command(args: argparse.Namespace) -> int:
    if args.samples_action == "list":
        for spec in SAMPLES_BY_SLUG.values():
            print(f"{spec.slug}\t{spec.name}")
        return 0
    generated = generate_sample_corpus(args.output, args.samples)
    print(json.dumps([item.to_dict() for item in generated], indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mesh2param",
        description="Compile and validate trusted Mesh2Param CADGraph documents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    compile_parser = subparsers.add_parser("compile", help="compile a CADGraph artifact bundle")
    compile_parser.add_argument("input", type=Path)
    compile_parser.add_argument("--output", type=Path, default=Path("artifacts"))
    compile_parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="ID=PATH",
        help="resolve a trusted imported feature artifact; repeat as needed",
    )
    compile_parser.set_defaults(handler=_compile_command)

    step_parser = subparsers.add_parser("validate-step", help="validate one STEP solid")
    step_parser.add_argument("path", type=Path)
    step_parser.add_argument("--units", choices=("mm", "cm", "m", "in", "ft"), default="mm")
    step_parser.set_defaults(handler=_validate_step_command)

    samples_parser = subparsers.add_parser("samples", help="list or generate procedural samples")
    sample_subparsers = samples_parser.add_subparsers(dest="samples_action", required=True)
    list_parser = sample_subparsers.add_parser("list", help="list the ten procedural samples")
    list_parser.set_defaults(handler=_samples_command)
    generate_parser = sample_subparsers.add_parser(
        "generate", help="generate deterministic sample artifacts"
    )
    generate_parser.add_argument("--output", type=Path, default=Path("samples/generated"))
    generate_parser.add_argument(
        "--sample",
        action="append",
        choices=tuple(SAMPLES_BY_SLUG),
        dest="samples",
    )
    generate_parser.set_defaults(handler=_samples_command)
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
    except (OSError, ValueError, KeyError, argparse.ArgumentTypeError) as exc:
        print(f"mesh2param: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__: list[str] = ["build_parser", "main"]
