"""Generate the deterministic Mesh2Param M1 procedural sample corpus."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from mesh2param.samples import SAMPLES_BY_SLUG, generate_sample_corpus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("samples/generated"),
        help="artifact root (default: samples/generated)",
    )
    parser.add_argument(
        "--sample",
        action="append",
        choices=tuple(SAMPLES_BY_SLUG),
        dest="samples",
        help="generate only this sample; repeat to select more than one",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    generated = generate_sample_corpus(args.output, args.samples)
    print(json.dumps([sample.to_dict() for sample in generated], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
