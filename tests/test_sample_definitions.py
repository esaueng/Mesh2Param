from __future__ import annotations

import math

import numpy as np
import pytest
from mesh2param.samples import SAMPLE_SPECS, sample_graph, sample_spec, sample_transform
from mesh2param_contracts import CADGraph, canonical_json


def test_all_ten_sample_graphs_are_strict_and_canonical() -> None:
    assert len(SAMPLE_SPECS) == 10
    assert len({spec.slug for spec in SAMPLE_SPECS}) == 10
    for spec in SAMPLE_SPECS:
        graph = spec.graph()
        encoded = canonical_json(graph)
        assert CADGraph.model_validate_json(encoded) == graph
        assert canonical_json(CADGraph.model_validate_json(encoded)) == encoded
        assert graph.deterministic_seed == 0x4D325000 + spec.ordinal
        assert graph.units == "mm"


def test_sample_lookup_reports_choices() -> None:
    assert sample_graph("rectangular-block") == SAMPLE_SPECS[0].graph()
    with pytest.raises(KeyError, match="unknown sample"):
        sample_spec("missing")


def test_bracket_seed_has_the_frozen_random_transform() -> None:
    spec = sample_spec("l-bracket-with-holes")
    frozen = sample_transform(spec)
    rng = np.random.Generator(np.random.PCG64(spec.seed))
    angles = (
        float(rng.integers(-300, 301)) / 10,
        float(rng.integers(-300, 301)) / 10,
        float(rng.integers(-600, 601)) / 10,
    )
    translation = tuple(float(rng.integers(-250, 251)) / 10 for _ in range(3))
    assert angles == (15.4, 19.0, -16.8)
    assert translation == (1.8, -13.8, -23.7)
    assert frozen.angles_deg == angles
    assert frozen.translation_mm == translation

    rx, ry, rz = (math.radians(value) for value in angles)
    rotation_x = np.array(
        ((1, 0, 0), (0, math.cos(rx), -math.sin(rx)), (0, math.sin(rx), math.cos(rx)))
    )
    rotation_y = np.array(
        ((math.cos(ry), 0, math.sin(ry)), (0, 1, 0), (-math.sin(ry), 0, math.cos(ry)))
    )
    rotation_z = np.array(
        ((math.cos(rz), -math.sin(rz), 0), (math.sin(rz), math.cos(rz), 0), (0, 0, 1))
    )
    actual = rotation_z @ rotation_y @ rotation_x
    expected = np.array(
        (
            (0.905163367700, 0.361420830414, 0.223728096396),
            (-0.273284932950, 0.897958617142, -0.344942991411),
            (-0.325568154457, 0.251088241948, 0.911570113353),
        )
    )
    assert np.allclose(actual, expected, rtol=0, atol=5e-13)
    assert np.allclose(frozen.rotation, expected, rtol=0, atol=5e-13)
