from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import cadquery as cq
import pytest
from mesh2param.validation import (
    export_step_validated,
    normalize_step_bytes,
    validate_shape,
)


def _raw_step(shape: cq.Shape, path: Path) -> bytes:
    cq.exporters.export(shape, str(path), exportType="STEP", unit="MM")
    return path.read_bytes()


def test_normalized_step_is_byte_stable_and_has_fixed_labels(tmp_path: Path) -> None:
    shape = cast(cq.Shape, cq.Workplane("XY").box(10, 8, 3).val())
    first_raw = _raw_step(shape, tmp_path / "random-first.step")
    second_raw = _raw_step(shape, tmp_path / "random-second.step")

    first = normalize_step_bytes(first_raw, model_name="stable model")
    second = normalize_step_bytes(second_raw, model_name="stable model")

    assert first == second
    assert b"\r" not in first
    assert first.endswith(b"\n") and not first.endswith(b"\n\n")
    text = first.decode("utf-8")
    assert "FILE_NAME('stable_model','1970-01-01T00:00:00'" in text
    assert len(re.findall(r"Open CASCADE STEP translator [0-9.]+ 1", text)) == 2


def test_normalizer_fails_closed_when_writer_labels_change(tmp_path: Path) -> None:
    shape = cast(cq.Shape, cq.Workplane("XY").box(2, 2, 2).val())
    raw = _raw_step(shape, tmp_path / "raw.step")
    text = raw.decode("utf-8")
    altered = text.replace("Open CASCADE STEP translator", "Unexpected translator", 1)

    with pytest.raises(ValueError, match="exactly two translator counters"):
        normalize_step_bytes(altered.encode("utf-8"))

    with pytest.raises(ValueError, match="exactly one FILE_NAME"):
        normalize_step_bytes(b"ISO-10303-21;\nEND-ISO-10303-21;\n")


def test_validated_step_reimports_and_repeated_export_is_identical(tmp_path: Path) -> None:
    shape = cast(
        cq.Shape,
        (
            cq.Workplane("XY")
            .box(20, 12, 5, centered=(True, True, False))
            .faces(">Z")
            .workplane()
            .hole(4)
            .val()
        ),
    )
    destination = tmp_path / "model.step"

    first = export_step_validated(shape, destination)
    first_bytes = destination.read_bytes()
    second = export_step_validated(shape, destination)

    assert first.valid and second.valid
    assert destination.read_bytes() == first_bytes
    assert first.sha256 == second.sha256
    assert first.reimport.solid_count == 1
    assert first.reimport.occt_valid
    assert first.volume_delta <= first.volume_tolerance
    assert ".model.step." not in first_bytes.decode("utf-8")


def test_kernel_only_validation_does_not_claim_tessellation() -> None:
    shape = cast(cq.Shape, cq.Workplane("XY").box(3, 4, 5).val())
    report = validate_shape(shape, require_tessellation=False)

    assert report.valid
    assert report.closed
    assert report.triangle_count == 0
    assert report.vertex_count == 0


def test_multi_solid_is_rejected() -> None:
    first = cast(cq.Shape, cq.Workplane("XY").box(2, 2, 2).val())
    second = first.translate((10, 0, 0))
    compound = cq.Compound.makeCompound([first, second])

    report = validate_shape(compound, require_tessellation=False)

    assert not report.valid
    assert report.solid_count == 2
    assert "expected exactly one solid" in report.errors[0]
