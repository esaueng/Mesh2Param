"""Command line entry point for the ``samples/real`` benchmark corpus tooling.

Usage: ``uv run python -m scripts.real_corpus <generate|ingest|audit|index>``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

# ``scripts`` is a namespace package, so importing it needs the repository root on the
# path. ``python -m scripts.real_corpus`` already has it; a direct file run does not.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.real_corpus.audit import ORIGINS, CorpusError, PartMetadata  # noqa: E402
from scripts.real_corpus.corpus import (  # noqa: E402
    DEFAULT_ROOT,
    REPOSITORY_LICENSE,
    audit_all,
    generate,
    index,
    ingest,
)


def _title_from_slug(slug: str) -> str:
    return " ".join(word.capitalize() for word in slug.split("-"))


def _tags(value: str) -> tuple[str, ...]:
    return tuple(tag.strip() for tag in value.split(",") if tag.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.real_corpus", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_root(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--out",
            "--root",
            dest="root",
            type=Path,
            default=DEFAULT_ROOT,
            help=f"corpus root (default: {DEFAULT_ROOT})",
        )

    generate_parser = subparsers.add_parser(
        "generate", help="rebuild STEP + STL + part.json for the procedural part library"
    )
    generate_parser.add_argument("--only", help="restrict the run to a single slug")
    generate_parser.add_argument(
        "--with-fine", action="store_true", help="also write the dense mesh-fine.stl tier"
    )
    add_root(generate_parser)

    ingest_parser = subparsers.add_parser(
        "ingest", help="copy user-supplied STEP/STL/3MF files into the corpus"
    )
    ingest_parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        help="path to a .step/.stp/.stl/.3mf file (or use --step/--stl/--threemf)",
    )
    ingest_parser.add_argument("--step", type=Path, help="STEP ground truth for this part")
    ingest_parser.add_argument("--stl", type=Path, help="user-supplied STL mesh")
    ingest_parser.add_argument("--threemf", type=Path, help="user-supplied 3MF mesh")
    ingest_parser.add_argument("--slug", required=True, help="corpus slug for the new part")
    ingest_parser.add_argument(
        "--origin", required=True, choices=[o for o in ORIGINS if o != "generated"]
    )
    ingest_parser.add_argument("--license", required=True, help="license or provenance statement")
    ingest_parser.add_argument("--title", help="human title (default: derived from the slug)")
    ingest_parser.add_argument("--tags", type=_tags, default=(), help="comma separated tag list")
    ingest_parser.add_argument("--units", choices=("mm", "in"), default="mm")
    ingest_parser.add_argument("--notes", default="", help="free-form provenance notes")
    ingest_parser.add_argument(
        "--featured", action="store_true", help="list this part first in the index and README"
    )
    ingest_parser.add_argument(
        "--force", action="store_true", help="replace an existing part directory"
    )
    ingest_parser.add_argument(
        "--with-fine", action="store_true", help="also write the dense mesh-fine.stl tier"
    )
    add_root(ingest_parser)

    audit_parser = subparsers.add_parser(
        "audit", help="recompute part.json for every part directory from the files on disk"
    )
    audit_parser.add_argument("--only", help="restrict the run to a single slug")
    add_root(audit_parser)

    index_parser = subparsers.add_parser("index", help="rewrite manifest.json and README.md")
    add_root(index_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root: Path = args.root
    try:
        if args.command == "generate":
            slugs = generate(root, args.only, with_fine=args.with_fine)
            print(f"generated {len(slugs)} part(s): {', '.join(slugs)}")
            print(f"indexed {index(root)} part(s) in {root}")
        elif args.command == "ingest":
            sources = [
                path
                for path in (args.source, args.step, args.stl, args.threemf)
                if path is not None
            ]
            if not sources:
                raise CorpusError("give a source path, or one of --step/--stl/--threemf")
            metadata = PartMetadata(
                slug=args.slug,
                title=args.title or _title_from_slug(args.slug),
                origin=args.origin,
                license=args.license or REPOSITORY_LICENSE,
                units=args.units,
                tags=tuple(args.tags),
                notes=args.notes,
                featured=args.featured,
            )
            directory = ingest(sources, root, metadata, force=args.force, with_fine=args.with_fine)
            listed = ", ".join(str(path) for path in sources)
            print(f"ingested {listed} -> {directory}")
            print(f"indexed {index(root)} part(s) in {root}")
        elif args.command == "audit":
            slugs = audit_all(root, args.only)
            print(f"audited {len(slugs)} part(s): {', '.join(slugs)}")
        else:
            print(f"indexed {index(root)} part(s) in {root}")
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
