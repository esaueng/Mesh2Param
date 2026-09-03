"""Score a ``*.segments.json`` against the analytic faces of its STEP ground truth.

Run from the worktree root::

    XDG_CACHE_HOME=.cache uv run --frozen python spikes/segmentation/compare.py \
        <segments.json> <samples/real/<slug>/model.step>

STEP faces that lie on the same analytic surface (a bore split into two half
cylinders, a plane split by a boolean) are merged into one *ground-truth
surface* first, because the segmenter has no reason to reproduce a kernel's
face splitting. Patches are then matched greedily, largest first.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from OCP.BRepAdaptor import BRepAdaptor_Surface  # noqa: E402
from OCP.BRepGProp import BRepGProp  # noqa: E402
from OCP.GProp import GProp_GProps  # noqa: E402
from OCP.TopAbs import TopAbs_ShapeEnum  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402

from scripts.real_corpus.audit import (  # noqa: E402
    _sub_shapes,
    _surface_name,
    load_step_shape,
)

#: Angle slack when two directions are called the same (degrees).
ANGLE_TOL_DEG = 2.0
#: Distance slack, as a fraction of the mesh bounding-box diagonal.
DIST_TOL_FRAC = 0.01
#: Radius slack, relative.
RADIUS_TOL_FRAC = 0.02

#: Types this spike can produce at all; everything else is out of scope by design.
FITTABLE = ("plane", "cylinder", "sphere")


def unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    n = math.sqrt(sum(c * c for c in v))
    return (0.0, 0.0, 0.0) if n == 0.0 else (v[0] / n, v[1] / n, v[2] / n)


def canonical_dir(v: tuple[float, float, float]) -> tuple[float, float, float]:
    """Direction with a deterministic sign, so a flipped axis compares equal."""
    u = unit(v)
    for c in u:
        if abs(c) > 1e-9:
            return u if c > 0 else (-u[0], -u[1], -u[2])
    return u


def dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b, strict=True))


def norm(a) -> float:
    return math.sqrt(dot(a, a))


def angle_undirected(a, b) -> float:
    return math.degrees(math.acos(min(1.0, max(-1.0, abs(dot(unit(a), unit(b)))))))


def foot_on_axis(point, direction):
    """Point of the line (point, direction) closest to the origin."""
    d = unit(direction)
    t = dot(point, d)
    return tuple(p - t * c for p, c in zip(point, d, strict=True))


def dist_point_line(q, p, d) -> float:
    rel = sub(q, p)
    t = dot(rel, unit(d))
    return norm(tuple(r - t * c for r, c in zip(rel, unit(d), strict=True)))


@dataclass
class Surface:
    kind: str
    normal: tuple[float, float, float] | None = None
    d: float = 0.0
    axis_point: tuple[float, float, float] | None = None
    axis_dir: tuple[float, float, float] | None = None
    radius: float = 0.0
    center: tuple[float, float, float] | None = None
    area: float = 0.0
    step_faces: int = 1
    matched_by: list[int] = field(default_factory=list)

    def describe(self) -> str:
        if self.kind == "plane":
            n = self.normal or (0, 0, 0)
            return f"plane n=({n[0]:.3f},{n[1]:.3f},{n[2]:.3f}) d={self.d:.3f}"
        if self.kind == "cylinder":
            a = self.axis_dir or (0, 0, 0)
            p = self.axis_point or (0, 0, 0)
            return (
                f"cylinder r={self.radius:.3f} axis=({a[0]:.3f},{a[1]:.3f},{a[2]:.3f})"
                f" through=({p[0]:.2f},{p[1]:.2f},{p[2]:.2f})"
            )
        if self.kind == "sphere":
            c = self.center or (0, 0, 0)
            return f"sphere r={self.radius:.3f} c=({c[0]:.2f},{c[1]:.2f},{c[2]:.2f})"
        return self.kind


def face_area(face) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return float(props.Mass())


def step_surfaces(path: Path) -> tuple[list[Surface], dict[str, int]]:
    shape = load_step_shape(path)
    faces = [TopoDS.Face_s(f) for f in _sub_shapes(shape, TopAbs_ShapeEnum.TopAbs_FACE)]
    raw_inventory: dict[str, int] = {}
    out: list[Surface] = []
    for face in faces:
        kind = _surface_name(face)
        raw_inventory[kind] = raw_inventory.get(kind, 0) + 1
        adaptor = BRepAdaptor_Surface(face)
        area = face_area(face)
        if kind == "plane":
            pln = adaptor.Plane()
            axis = pln.Axis()
            n = canonical_dir(tuple(axis.Direction().Coord()))
            loc = tuple(axis.Location().Coord())
            out.append(Surface("plane", normal=n, d=dot(n, loc), area=area))
        elif kind == "cylinder":
            cyl = adaptor.Cylinder()
            axis = cyl.Axis()
            a = canonical_dir(tuple(axis.Direction().Coord()))
            out.append(
                Surface(
                    "cylinder",
                    axis_dir=a,
                    axis_point=foot_on_axis(tuple(axis.Location().Coord()), a),
                    radius=float(cyl.Radius()),
                    area=area,
                )
            )
        elif kind == "sphere":
            sph = adaptor.Sphere()
            out.append(
                Surface(
                    "sphere",
                    center=tuple(sph.Location().Coord()),
                    radius=float(sph.Radius()),
                    area=area,
                )
            )
        else:
            out.append(Surface(kind, area=area))
    return out, raw_inventory


def same_surface(a: Surface, b: Surface, dist_tol: float) -> bool:
    if a.kind != b.kind:
        return False
    if a.kind == "plane":
        if angle_undirected(a.normal, b.normal) > ANGLE_TOL_DEG:
            return False
        flip = 1.0 if dot(a.normal, b.normal) >= 0 else -1.0
        return abs(a.d - flip * b.d) <= dist_tol
    if a.kind == "cylinder":
        return (
            angle_undirected(a.axis_dir, b.axis_dir) <= ANGLE_TOL_DEG
            and abs(a.radius - b.radius) <= RADIUS_TOL_FRAC * max(a.radius, b.radius)
            and dist_point_line(b.axis_point, a.axis_point, a.axis_dir) <= dist_tol
        )
    if a.kind == "sphere":
        return norm(sub(a.center, b.center)) <= dist_tol and abs(a.radius - b.radius) <= (
            RADIUS_TOL_FRAC * max(a.radius, b.radius)
        )
    return False


def merge_surfaces(surfaces: list[Surface], dist_tol: float) -> list[Surface]:
    """Collapse STEP faces that lie on one analytic surface into one entry."""
    merged: list[Surface] = []
    for s in surfaces:
        if s.kind not in FITTABLE:
            merged.append(s)
            continue
        for m in merged:
            if same_surface(m, s, dist_tol):
                m.area += s.area
                m.step_faces += 1
                break
        else:
            merged.append(s)
    return merged


def patch_surface(patch: dict[str, Any]) -> Surface | None:
    kind = patch["type"]
    if kind == "plane":
        n = canonical_dir(tuple(patch["plane"]["normal"]))
        flip = 1.0 if dot(n, patch["plane"]["normal"]) >= 0 else -1.0
        return Surface("plane", normal=n, d=flip * patch["plane"]["d"], area=patch["area"])
    if kind == "cylinder":
        a = canonical_dir(tuple(patch["cylinder"]["axisDir"]))
        return Surface(
            "cylinder",
            axis_dir=a,
            axis_point=foot_on_axis(tuple(patch["cylinder"]["axisPoint"]), a),
            radius=float(patch["cylinder"]["radius"]),
            area=patch["area"],
        )
    if kind == "sphere":
        return Surface(
            "sphere",
            center=tuple(patch["sphere"]["center"]),
            radius=float(patch["sphere"]["radius"]),
            area=patch["area"],
        )
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <segments.json> <model.step>", file=sys.stderr)
        return 2
    seg_path = Path(argv[1])
    step_path = Path(argv[2])
    seg = json.loads(seg_path.read_text())
    diag = float(seg["bboxDiagonal"])
    dist_tol = DIST_TOL_FRAC * diag

    raw, raw_inventory = step_surfaces(step_path)
    truth = merge_surfaces(raw, dist_tol)
    gt_fittable = [s for s in truth if s.kind in FITTABLE]
    gt_other = [s for s in truth if s.kind not in FITTABLE]

    patches = seg["patches"]
    total_area = sum(p["area"] for p in patches) or 1.0
    known = [p for p in patches if p["type"] in FITTABLE]
    known.sort(key=lambda p: -p["area"])

    matched: list[tuple[dict, Surface]] = []
    duplicates: list[tuple[dict, Surface]] = []
    spurious: list[dict] = []
    for p in known:
        s = patch_surface(p)
        hit = next((g for g in gt_fittable if same_surface(g, s, dist_tol)), None)
        if hit is None:
            spurious.append(p)
        elif hit.matched_by:
            hit.matched_by.append(p["id"])
            duplicates.append((p, hit))
        else:
            hit.matched_by.append(p["id"])
            matched.append((p, hit))
    missed = [g for g in gt_fittable if not g.matched_by]

    def by_kind(items, key) -> dict[str, int]:
        out: dict[str, int] = {}
        for it in items:
            k = key(it)
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items()))

    gt_counts = by_kind(truth, lambda s: s.kind)
    rec_counts = by_kind(patches, lambda p: p["type"])
    missed_area = sum(g.area for g in missed)
    gt_area = sum(g.area for g in gt_fittable) or 1.0

    print(f"stl              {seg['stl']}")
    print(f"step             {step_path}")
    print(f"triangles        {seg['triangles']}   bboxDiag {diag:.3f}   distTol {dist_tol:.3f}")
    print(f"STEP faces       {sum(raw_inventory.values())}  {raw_inventory}")
    print(f"ground truth     {gt_counts}   (coincident faces merged)")
    print(f"recovered        {rec_counts}")
    print(
        f"matched {len(matched)}/{len(gt_fittable)} fittable surfaces"
        f"   duplicates {len(duplicates)}   spurious {len(spurious)}"
    )
    print(
        f"missed {len(missed)} ({100 * missed_area / gt_area:.1f}% of fittable GT area)"
        f"   out-of-scope GT faces (cone/torus/bspline/...) {len(gt_other)}"
    )
    print(f"unknown area fraction {seg['unknownAreaFraction']:.4f}")

    if missed:
        print("\nmissed ground-truth surfaces (up to 10):")
        for g in sorted(missed, key=lambda s: -s.area)[:10]:
            print(f"  area={g.area:10.2f} stepFaces={g.step_faces}  {g.describe()}")
    if spurious:
        print("\nspurious patches (up to 10, largest first):")
        for p in sorted(spurious, key=lambda x: -x["area"])[:10]:
            s = patch_surface(p)
            frac = 100 * p["area"] / total_area
            print(f"  id={p['id']:4d} area={p['area']:10.2f} ({frac:5.2f}%)  {s.describe()}")

    report = {
        "segments": str(seg_path),
        "step": str(step_path),
        "triangles": seg["triangles"],
        "bboxDiagonal": diag,
        "distTol": dist_tol,
        "stepFaceInventory": raw_inventory,
        "groundTruthSurfaces": gt_counts,
        "groundTruthFittable": len(gt_fittable),
        "groundTruthOutOfScope": len(gt_other),
        "recovered": rec_counts,
        "matched": len(matched),
        "duplicates": len(duplicates),
        "spurious": len(spurious),
        "missed": len(missed),
        "missedAreaFraction": missed_area / gt_area,
        "spuriousAreaFraction": sum(p["area"] for p in spurious) / total_area,
        "unknownAreaFraction": seg["unknownAreaFraction"],
        "missedList": [
            {"kind": g.kind, "area": g.area, "stepFaces": g.step_faces, "desc": g.describe()}
            for g in sorted(missed, key=lambda s: -s.area)[:10]
        ],
        "spuriousList": [
            {
                "id": p["id"],
                "kind": p["type"],
                "area": p["area"],
                "areaFraction": p["area"] / total_area,
                "desc": (patch_surface(p) or Surface("unknown")).describe(),
            }
            for p in sorted(spurious, key=lambda x: -x["area"])[:10]
        ],
    }
    out_path = seg_path.with_name(seg_path.name.replace(".segments.json", ".compare.json"))
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
