"""Generate the deterministic curved-reconstruction benchmark fixture corpus."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from mesh2param.curved_fixtures import CURVED_FIXTURES_BY_SLUG, generate_curved_fixture_corpus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("samples/curved-benchmark"),
        help="fixture root (default: samples/curved-benchmark)",
    )
    parser.add_argument(
        "--fixture",
        action="append",
        choices=tuple(CURVED_FIXTURES_BY_SLUG),
        dest="fixtures",
        help="generate only this fixture; repeat to select more than one",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    generated = generate_curved_fixture_corpus(args.output, args.fixtures)
    print(json.dumps([fixture.to_dict() for fixture in generated], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
