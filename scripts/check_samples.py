"""Regenerate samples and strictly compare them with the committed corpus."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import shutil
import stat
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_STEP_ARTIFACT = "model.step"
_STEP_METADATA = "metadata.json"
_STEP_MANIFEST = "manifest.json"
_STEP_CASCADE_ARTIFACTS = frozenset({_STEP_ARTIFACT, _STEP_METADATA, _STEP_MANIFEST})
# PR #58 exposed +/-1e-12 mm coordinate serialization drift. Bounds, area and
# volume comparisons use a 1e-10 relative limit plus explicit mm-based floors:
# platform margin remains at least three orders above the observed coordinate
# noise while the relative limit stays four orders tighter than the existing
# 1e-6 STEP reimport-volume gate.
_STEP_EQUIVALENCE_RELATIVE_TOLERANCE = 1e-10
_STEP_EQUIVALENCE_ABSOLUTE_LINEAR_MM = 1e-9
_STEP_EQUIVALENCE_ABSOLUTE_AREA_MM2 = 1e-9
_STEP_EQUIVALENCE_ABSOLUTE_VOLUME_MM3 = 1e-9


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
    equivalent_step_serializations: tuple[str, ...] = ()
    step_validation_errors: tuple[str, ...] = ()

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
            "equivalentStepSerializations": list(self.equivalent_step_serializations),
            "stepValidationErrors": list(self.step_validation_errors),
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


def _json_object(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path.name} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return document


def _validated_manifest(sample_root: Path) -> dict[str, object]:
    manifest = _json_object(sample_root / _STEP_MANIFEST)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("manifest.json artifacts must be a list")

    artifact_records: dict[str, dict[str, object]] = {}
    for record in artifacts:
        if not isinstance(record, dict):
            raise ValueError("manifest.json artifact entries must be objects")
        name = record.get("name")
        byte_size = record.get("byteSize")
        sha256 = record.get("sha256")
        if not isinstance(name, str) or Path(name).name != name or name in artifact_records:
            raise ValueError(f"manifest.json has an invalid artifact name: {name!r}")
        if not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size < 0:
            raise ValueError(f"manifest.json has an invalid byteSize for {name}")
        if (
            not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
        ):
            raise ValueError(f"manifest.json has an invalid sha256 for {name}")
        artifact_records[name] = record

    actual_artifacts = {
        path.name
        for path in sample_root.iterdir()
        if path.is_file() and path.name != _STEP_MANIFEST
    }
    if set(artifact_records) != actual_artifacts:
        raise ValueError("manifest.json artifact inventory does not match the sample directory")
    for name, record in artifact_records.items():
        path = sample_root / name
        if path.stat().st_size != record["byteSize"]:
            raise ValueError(f"manifest.json byteSize does not match {name}")
        if _hash_file(path) != record["sha256"]:
            raise ValueError(f"manifest.json sha256 does not match {name}")
    return manifest


def _validated_metadata(sample_root: Path) -> dict[str, object]:
    metadata = _json_object(sample_root / _STEP_METADATA)
    step = metadata.get("step")
    if not isinstance(step, dict):
        raise ValueError("metadata.json step must be an object")
    step_path = sample_root / _STEP_ARTIFACT
    if step.get("sha256") != _hash_file(step_path):
        raise ValueError("metadata.json STEP sha256 does not match model.step")
    for field in ("sourceValid", "reimportValid", "topologyCountsMatch"):
        if step.get(field) is not True:
            raise ValueError(f"metadata.json STEP guarantee {field} is not true")
    volume_delta = step.get("volumeDelta")
    volume_tolerance = step.get("volumeTolerance")
    if (
        not isinstance(volume_delta, (int, float))
        or isinstance(volume_delta, bool)
        or not math.isfinite(volume_delta)
        or volume_delta < 0.0
    ):
        raise ValueError("metadata.json STEP volumeDelta is invalid")
    if (
        not isinstance(volume_tolerance, (int, float))
        or isinstance(volume_tolerance, bool)
        or not math.isfinite(volume_tolerance)
        or volume_tolerance <= 0.0
    ):
        raise ValueError("metadata.json STEP volumeTolerance is invalid")
    if volume_delta > volume_tolerance:
        raise ValueError("metadata.json STEP volumeDelta exceeds its volumeTolerance")
    return metadata


def _normalized_step_metadata(metadata: dict[str, object]) -> dict[str, object]:
    normalized = copy.deepcopy(metadata)
    step = normalized["step"]
    assert isinstance(step, dict)
    step["sha256"] = "<kernel-validated-step>"
    step["volumeDelta"] = "<within-recorded-tolerance>"
    return normalized


def _normalized_step_manifest(manifest: dict[str, object]) -> dict[str, object]:
    normalized = copy.deepcopy(manifest)
    artifacts = normalized["artifacts"]
    assert isinstance(artifacts, list)
    for record in artifacts:
        assert isinstance(record, dict)
        if record["name"] in {_STEP_ARTIFACT, _STEP_METADATA}:
            record["byteSize"] = "<integrity-validated>"
            record["sha256"] = "<integrity-validated>"
    return normalized


def _bounding_box_coordinates(shape: object) -> tuple[float, ...]:
    bounds = shape.BoundingBox()  # type: ignore[attr-defined]
    return (
        float(bounds.xmin),
        float(bounds.ymin),
        float(bounds.zmin),
        float(bounds.xmax),
        float(bounds.ymax),
        float(bounds.zmax),
    )


def _step_geometry_errors(expected_path: Path, generated_path: Path) -> tuple[str, ...]:
    # Keep CadQuery/OCP imports out of simple inventory-only callers.
    from mesh2param.validation import (
        classify_parametric_face_surfaces,
        import_step_shape,
        validate_shape,
    )

    errors: list[str] = []
    try:
        expected_shape = import_step_shape(expected_path)
        generated_shape = import_step_shape(generated_path)
        expected_validation = validate_shape(
            expected_shape,
            linear_resolution=0.025,
            angular_tolerance=math.radians(2.0),
        )
        generated_validation = validate_shape(
            generated_shape,
            linear_resolution=0.025,
            angular_tolerance=math.radians(2.0),
        )
    except Exception as exc:
        return (f"STEP import or kernel validation raised {type(exc).__name__}: {exc}",)

    if not expected_validation.valid:
        errors.append(
            "committed STEP failed live kernel validation: " + "; ".join(expected_validation.errors)
        )
    if not generated_validation.valid:
        errors.append(
            "regenerated STEP failed live kernel validation: "
            + "; ".join(generated_validation.errors)
        )

    integer_fields = (
        "solid_count",
        "face_count",
        "edge_count",
    )
    for field in integer_fields:
        expected_value = getattr(expected_validation, field)
        generated_value = getattr(generated_validation, field)
        if expected_value != generated_value:
            errors.append(f"STEP {field} changed from {expected_value} to {generated_value}")
    expected_topological_vertices = len(expected_shape.Vertices())
    generated_topological_vertices = len(generated_shape.Vertices())
    if expected_topological_vertices != generated_topological_vertices:
        errors.append(
            "STEP topological vertex count changed from "
            f"{expected_topological_vertices} to {generated_topological_vertices}"
        )

    expected_surfaces = classify_parametric_face_surfaces(expected_shape)
    generated_surfaces = classify_parametric_face_surfaces(generated_shape)
    if expected_surfaces != generated_surfaces:
        errors.append(
            f"STEP surface classes changed from {expected_surfaces} to {generated_surfaces}"
        )

    volume_scale = max(
        abs(expected_validation.volume),
        abs(generated_validation.volume),
        1.0,
    )
    volume_tolerance = max(
        volume_scale * _STEP_EQUIVALENCE_RELATIVE_TOLERANCE,
        _STEP_EQUIVALENCE_ABSOLUTE_VOLUME_MM3,
    )
    volume_delta = abs(expected_validation.volume - generated_validation.volume)
    if not math.isfinite(volume_delta) or volume_delta > volume_tolerance:
        errors.append(f"STEP volume delta {volume_delta:g} exceeds {volume_tolerance:g} mm^3")

    area_scale = max(
        abs(expected_validation.area),
        abs(generated_validation.area),
        1.0,
    )
    area_tolerance = max(
        area_scale * _STEP_EQUIVALENCE_RELATIVE_TOLERANCE,
        _STEP_EQUIVALENCE_ABSOLUTE_AREA_MM2,
    )
    area_delta = abs(expected_validation.area - generated_validation.area)
    if not math.isfinite(area_delta) or area_delta > area_tolerance:
        errors.append(f"STEP area delta {area_delta:g} exceeds {area_tolerance:g} mm^2")

    expected_bounds = _bounding_box_coordinates(expected_shape)
    generated_bounds = _bounding_box_coordinates(generated_shape)
    linear_scale = max(
        *(abs(value) for value in expected_bounds),
        *(abs(value) for value in generated_bounds),
        1.0,
    )
    linear_tolerance = max(
        linear_scale * _STEP_EQUIVALENCE_RELATIVE_TOLERANCE,
        _STEP_EQUIVALENCE_ABSOLUTE_LINEAR_MM,
    )
    maximum_bounds_delta = max(
        abs(expected - generated)
        for expected, generated in zip(expected_bounds, generated_bounds, strict=True)
    )
    if not math.isfinite(maximum_bounds_delta) or maximum_bounds_delta > linear_tolerance:
        errors.append(
            f"STEP bounding-box delta {maximum_bounds_delta:g} exceeds {linear_tolerance:g} mm"
        )

    try:
        expected_only_volume = abs(float(expected_shape.cut(generated_shape).Volume()))
        generated_only_volume = abs(float(generated_shape.cut(expected_shape).Volume()))
    except Exception as exc:
        errors.append(f"STEP symmetric-difference proof raised {type(exc).__name__}: {exc}")
    else:
        for label, unmatched_volume in (
            ("committed-only", expected_only_volume),
            ("regenerated-only", generated_only_volume),
        ):
            if not math.isfinite(unmatched_volume) or unmatched_volume > volume_tolerance:
                errors.append(
                    f"STEP {label} volume {unmatched_volume:g} exceeds {volume_tolerance:g} mm^3"
                )
    return tuple(errors)


def _equivalent_step_serialization_errors(
    expected_root: Path,
    generated_root: Path,
) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        expected_metadata = _validated_metadata(expected_root)
        generated_metadata = _validated_metadata(generated_root)
        if _normalized_step_metadata(expected_metadata) != _normalized_step_metadata(
            generated_metadata
        ):
            errors.append(
                "metadata.json changed outside the validated STEP hash and round-trip delta"
            )

        expected_manifest = _validated_manifest(expected_root)
        generated_manifest = _validated_manifest(generated_root)
        if _normalized_step_manifest(expected_manifest) != _normalized_step_manifest(
            generated_manifest
        ):
            errors.append(
                "manifest.json changed outside the integrity-validated STEP and metadata records"
            )
    except (OSError, ValueError) as exc:
        errors.append(str(exc))

    errors.extend(
        _step_geometry_errors(
            expected_root / _STEP_ARTIFACT,
            generated_root / _STEP_ARTIFACT,
        )
    )
    return tuple(errors)


def compare_sample_trees(expected_root: Path, generated_root: Path) -> SampleTreeComparison:
    expected = fingerprint_tree(expected_root)
    generated = fingerprint_tree(generated_root)
    expected_paths = set(expected)
    generated_paths = set(generated)
    shared_paths = expected_paths & generated_paths
    changed = {path for path in shared_paths if expected[path] != generated[path]}
    equivalent_step_serializations: list[str] = []
    step_validation_errors: list[str] = []
    changed_steps = sorted(path for path in changed if Path(path).name == _STEP_ARTIFACT)
    for step_path in changed_steps:
        sample_relative = Path(step_path).parent
        expected_sample = expected_root / sample_relative
        generated_sample = generated_root / sample_relative
        errors = _equivalent_step_serialization_errors(
            expected_sample,
            generated_sample,
        )
        if errors:
            step_validation_errors.extend(f"{step_path}: {error}" for error in errors)
            continue
        accepted_paths = {(sample_relative / name).as_posix() for name in _STEP_CASCADE_ARTIFACTS}
        changed.difference_update(accepted_paths)
        equivalent_step_serializations.append(step_path)

    return SampleTreeComparison(
        missing=tuple(sorted(expected_paths - generated_paths)),
        unexpected=tuple(sorted(generated_paths - expected_paths)),
        changed=tuple(sorted(changed)),
        file_count=len(expected),
        equivalent_step_serializations=tuple(equivalent_step_serializations),
        step_validation_errors=tuple(step_validation_errors),
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
    parser.add_argument(
        "--generated-output",
        type=Path,
        help="copy the regenerated corpus here when the comparison fails",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from mesh2param.samples import generate_sample_corpus

    with tempfile.TemporaryDirectory(prefix="mesh2param-samples-check-") as temporary:
        regenerated = Path(temporary) / "generated"
        generate_sample_corpus(regenerated)
        comparison = compare_sample_trees(args.expected.resolve(), regenerated)
        if not comparison.matches and args.generated_output is not None:
            generated_output = args.generated_output.resolve()
            generated_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(regenerated, generated_output, copy_function=shutil.copyfile)

    payload = comparison.to_dict()
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if comparison.matches:
        if comparison.equivalent_step_serializations:
            print(
                "sample corpus is semantically stable "
                f"({comparison.file_count} files; "
                f"{len(comparison.equivalent_step_serializations)} "
                "kernel-equivalent STEP serialization difference(s))"
            )
        else:
            print(f"sample corpus is byte-stable ({comparison.file_count} files)")
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
