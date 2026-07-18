"""Probe that the locked stack can fit, solidify, and round-trip a B-spline STEP.

Fits a deterministic non-round 9 by 9 wavy point grid with
``GeomAPI_PointsToBSplineSurface``, thickens the fitted surface into one solid,
exports normalized STEP through the repository's validated exporter, reimports
it with the OCCT kernel, and requires B-spline faces to survive the round trip.
This is the feasibility evidence cited by docs/curved-step-reconstruction.md.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Sequence
from math import cos, sin
from pathlib import Path

import cadquery as cq
from mesh2param.validation import (
    classify_face_surfaces,
    export_step_validated,
    import_step_shape,
    validate_shape,
)
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
from OCP.gp import gp_Pnt, gp_Vec
from OCP.TColgp import TColgp_Array2OfPnt

GRID_SIZE = 9
GRID_SPACING_MM = 10.0
WAVE_AMPLITUDE_MM = 4.0
THICKNESS_MM = 30.0


def wavy_grid() -> TColgp_Array2OfPnt:
    """Build a deterministic non-round height field no analytic surface matches."""

    points = TColgp_Array2OfPnt(1, GRID_SIZE, 1, GRID_SIZE)
    for row in range(1, GRID_SIZE + 1):
        for column in range(1, GRID_SIZE + 1):
            x = (row - 1) * GRID_SPACING_MM
            y = (column - 1) * GRID_SPACING_MM
            z = WAVE_AMPLITUDE_MM * sin(x / 12.0) * cos(y / 15.0) + 0.05 * x
            points.SetValue(row, column, gp_Pnt(x, y, z))
    return points


def fitted_solid() -> tuple[cq.Shape, str]:
    fitter = GeomAPI_PointsToBSplineSurface(wavy_grid())
    if not fitter.IsDone():
        raise ValueError("GeomAPI_PointsToBSplineSurface did not converge")
    surface = fitter.Surface()
    face = BRepBuilderAPI_MakeFace(surface, 1e-6).Face()
    prism = BRepPrimAPI_MakePrism(face, gp_Vec(0.0, 0.0, -THICKNESS_MM))
    return cq.Shape.cast(prism.Shape()), type(surface).__name__


def run_probe(step_path: Path) -> dict[str, object]:
    solid, surface_type = fitted_solid()
    source_faces = classify_face_surfaces(solid)
    report = export_step_validated(solid, step_path, units="mm")
    reimported = import_step_shape(step_path, units="mm")
    reimport_faces = classify_face_surfaces(reimported)
    step_text = step_path.read_text(encoding="utf-8")

    checks = {
        "fittedSurfaceIsBSpline": surface_type == "Geom_BSplineSurface",
        "solidValid": validate_shape(solid).valid,
        "sourceHasBSplineFaces": source_faces["bspline"] >= 1,
        "stepRoundTripValid": report.valid,
        "stepContainsBSplineEntity": "B_SPLINE_SURFACE" in step_text,
        "reimportHasBSplineFaces": reimport_faces["bspline"] >= 1,
        "faceTypesSurviveReimport": source_faces == reimport_faces,
    }
    return {
        "fittedSurfaceType": surface_type,
        "sourceFaceSurfaces": source_faces,
        "reimportFaceSurfaces": reimport_faces,
        "step": report.to_dict(),
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="keep the probe STEP file at this path (default: temporary file)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.output is not None:
        result = run_probe(args.output)
    else:
        with tempfile.TemporaryDirectory() as scratch:
            result = run_probe(Path(scratch) / "probe_bspline.step")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
