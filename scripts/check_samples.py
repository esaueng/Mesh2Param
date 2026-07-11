"""Regenerate samples outside the checkout and compare the exact committed corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    byte_size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SampleTreeComparison:
    missing: tuple[str, ...]
    unexpected: tuple[str, ...]
    changed: tuple[str, ...]
    file_count: int

    @property
    def matches(self) -> bool:
        return not (self.missing or self.unexpected or self.changed)

    def to_dict(self) -> dict[str, object]:
        return {
            "matches": self.matches,
            "missing": list(self.missing),
            "unexpected": list(self.unexpected),
            "changed": list(self.changed),
            "fileCount": self.file_count,
        }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_tree(root: Path) -> dict[str, FileFingerprint]:
    """Return a deterministic inventory while rejecting links and special files."""

    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"sample root must be a real directory: {root}")
    inventory: dict[str, FileFingerprint] = {}
    for path in sorted(root.rglob("*")):
        status = path.lstat()
        relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(status.st_mode):
            raise ValueError(f"sample corpus cannot contain symlinks: {relative}")
        if stat.S_ISDIR(status.st_mode):
            continue
        if not stat.S_ISREG(status.st_mode):
            raise ValueError(f"sample corpus contains a non-regular file: {relative}")
        inventory[relative] = FileFingerprint(
            byte_size=status.st_size,
            sha256=_hash_file(path),
        )
    return inventory


def compare_sample_trees(expected_root: Path, generated_root: Path) -> SampleTreeComparison:
    expected = fingerprint_tree(expected_root)
    generated = fingerprint_tree(generated_root)
    expected_paths = set(expected)
    generated_paths = set(generated)
    shared_paths = expected_paths & generated_paths
    return SampleTreeComparison(
        missing=tuple(sorted(expected_paths - generated_paths)),
        unexpected=tuple(sorted(generated_paths - expected_paths)),
        changed=tuple(
            sorted(path for path in shared_paths if expected[path] != generated[path])
        ),
        file_count=len(expected),
    )


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expected",
        type=Path,
        default=repository_root / "samples" / "generated",
        help="committed generated sample tree",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="optional machine-readable comparison output",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from mesh2param.samples import generate_sample_corpus

    with tempfile.TemporaryDirectory(prefix="mesh2param-samples-check-") as temporary:
        regenerated = Path(temporary) / "generated"
        generate_sample_corpus(regenerated)
        comparison = compare_sample_trees(args.expected.resolve(), regenerated)

    payload = comparison.to_dict()
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if comparison.matches:
        print(f"sample corpus is deterministic ({comparison.file_count} files)")
        return 0
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FileFingerprint",
    "SampleTreeComparison",
    "compare_sample_trees",
    "fingerprint_tree",
    "main",
]
