"""Prove that the locked OCCT stack round-trips a non-round B-spline STEP solid."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cadquery as cq
from mesh2param.validation import (
    classify_face_surfaces,
    export_step_validated,
    import_step_shape,
)
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
from OCP.gp import gp_Pnt
from OCP.TColgp import TColgp_Array2OfPnt


def _curved_point_grid() -> TColgp_Array2OfPnt:
    points = TColgp_Array2OfPnt(1, 9, 1, 9)
    for row in range(1, 10):
        x = (row - 1) * 5.0
        for column in range(1, 10):
            y = (column - 1) * 5.0
            z = 2.2 * math.sin(math.pi * x / 40.0) * math.sin(math.pi * y / 40.0)
            z += 0.35 * math.sin(2.0 * math.pi * x / 40.0) * math.sin(
                math.pi * y / 40.0
            )
            points.SetValue(row, column, gp_Pnt(x, y, z))
    return points


def run_probe(output: Path) -> dict[str, object]:
    fitter = GeomAPI_PointsToBSplineSurface(_curved_point_grid(), 3, 5, Tol3D=0.01)
    if not fitter.IsDone():
        raise RuntimeError("OCCT failed to fit the B-spline probe surface")

    face = cq.Face(BRepBuilderAPI_MakeFace(fitter.Surface(), 1.0e-6).Face())
    solid = face.thicken(-4.0)
    validation = export_step_validated(
        solid,
        output,
        units="mm",
        linear_resolution=1.0e-3,
        angular_tolerance=0.1,
    )
    surface_types = classify_face_surfaces(import_step_shape(output))
    if surface_types["bspline"] < 1:
        raise RuntimeError("STEP roundtrip did not retain a B-spline face")
    return {
        "path": str(output),
        "valid": validation.valid,
        "solidCount": validation.reimport.solid_count,
        "faceCount": validation.reimport.face_count,
        "surfaceTypes": surface_types,
        "sha256": validation.sha256,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="destination .step or .stp file")
    args = parser.parse_args()
    result = run_probe(args.output.resolve())
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
