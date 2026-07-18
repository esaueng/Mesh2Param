"""Deterministic curved-reconstruction benchmark fixtures (Milestone 0).

Every positive fixture is tessellated from a procedural ground-truth B-Rep
whose top face is a genuine non-round B-spline surface, so future curved
reconstruction can be scored against exact geometry instead of another mesh.
Negative fixtures are hand-built triangle meshes that violate one specific
qualification rule (open, non-manifold, self-intersecting, coarse, or
multi-body). Generation is fully deterministic: the same specs always produce
byte-identical STL artifacts and manifests.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import cos, pi, sin
from pathlib import Path
from typing import Any, Literal

import cadquery as cq
import numpy as np
import trimesh
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
from OCP.gp import gp_Pnt, gp_Vec
from OCP.TColgp import TColgp_Array2OfPnt

from .curved_patch import PLATE_ARTIFACT_SCHEMA, assemble_single_patch_plate, rebuild_plate_solid
from .surface_fit import build_occt_bspline_surface, greville_abscissae, open_uniform_knots
from .surface_network import NetworkCurve, NetworkPatch, NetworkVertex, SurfaceNetwork
from .tessellation import tessellate_shape
from .validation import classify_face_surfaces, validate_shape

FixtureCategory = Literal["positive", "negative"]
FixtureExpectation = Literal[
    "closed-manifold",
    "closed-manifold-coarse",
    "open-surface",
    "non-manifold",
    "self-intersecting",
    "multi-body",
]

FIXTURE_STL_NAME = "source.stl"
FIXTURE_MANIFEST_NAME = "fixture.json"
CORPUS_MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True, slots=True)
class CurvedFixtureSpec:
    """One deterministic benchmark input and how a qualifier should judge it."""

    slug: str
    title: str
    category: FixtureCategory
    expectation: FixtureExpectation
    description: str
    units: str = "mm"
    linear_tolerance: float = 0.2
    angular_tolerance: float = 0.3
    noise_amplitude: float = 0.0
    noise_seed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "category": self.category,
            "expectation": self.expectation,
            "description": self.description,
            "units": self.units,
            "tessellation": {
                "linearTolerance": self.linear_tolerance,
                "angularTolerance": self.angular_tolerance,
            },
            "noise": {"amplitude": self.noise_amplitude, "seed": self.noise_seed},
        }


def _wavy_bspline_solid(
    *,
    grid: int = 9,
    spacing: float = 10.0,
    amplitude: float = 4.0,
    x_period: float = 12.0,
    y_period: float = 15.0,
    tilt: float = 0.05,
    thickness: float = 30.0,
    scale: float = 1.0,
) -> cq.Shape:
    """Thicken a fitted non-round wavy B-spline sheet into one closed solid.

    The top face is a real ``Geom_BSplineSurface`` and its junctions with the
    extruded walls are sharp creases, so every derived fixture carries both a
    freeform region and true C0 feature edges.
    """

    points = TColgp_Array2OfPnt(1, grid, 1, grid)
    for row in range(1, grid + 1):
        for column in range(1, grid + 1):
            x = (row - 1) * spacing
            y = (column - 1) * spacing
            z = amplitude * sin(x / x_period) * cos(y / y_period) + tilt * x
            points.SetValue(row, column, gp_Pnt(x * scale, y * scale, z * scale))
    fitter = GeomAPI_PointsToBSplineSurface(points)
    if not fitter.IsDone():
        raise ValueError("wavy fixture B-spline fit did not converge")
    face = BRepBuilderAPI_MakeFace(fitter.Surface(), 1e-6).Face()
    prism = BRepPrimAPI_MakePrism(face, gp_Vec(0.0, 0.0, -thickness * scale))
    return cq.Shape.cast(prism.Shape())


def _bump_plate_solid(scale: float = 1.0) -> cq.Shape:
    """A plate whose only curved face is one exact bicubic B-spline bump.

    Boundary poles lie exactly on a planar rectangle, so the freeform top
    meets four true planes and a planar bottom at straight C0 creases: the
    canonical Milestone 1 single-patch reconstruction target (5 planes plus
    1 B-spline face).
    """

    degree = 3
    control = 7
    size = 80.0 * scale
    height = 25.0 * scale
    knots = open_uniform_knots(control, degree)
    greville = greville_abscissae(knots, degree)
    poles = np.zeros((control, control, 3))
    for i, gu in enumerate(greville):
        for j, gv in enumerate(greville):
            poles[i, j, 0] = gu * size
            poles[i, j, 1] = gv * size
            interior = 0 < i < control - 1 and 0 < j < control - 1
            if interior:
                poles[i, j, 2] = (6.0 * scale * sin(pi * gu) * sin(pi * gv)) * (1.0 + 0.35 * gu)
    surface = build_occt_bspline_surface(poles, knots, knots, degree)
    corners = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [size, 0.0, 0.0],
            [size, size, 0.0],
            [0.0, size, 0.0],
        ]
    )
    return assemble_single_patch_plate(
        surface, corners, np.asarray([0.0, 0.0, -height]), sewing_tolerance=1e-6
    )


def _gable_plate_solid(
    scale: float = 1.0,
    *,
    ridge_poles: tuple[float, ...] = (10.0, 11.5, 14.0, 12.5, 13.5, 11.5, 10.0),
    bumps: tuple[float, float] = (3.0, 2.2),
) -> cq.Shape:
    """A plate whose top is two exact B-spline roofs meeting at a sharp crease.

    The ridge is an elevated, bowed cubic curve shared pole-for-pole by both
    roof patches, so the ground truth is a true two-patch crease network: G0
    exact along the ridge with a dihedral angle everywhere above the
    segmentation crease threshold (the ridge endpoints stay elevated, making
    the end walls planar pentagons). Built through the same artifact rebuild
    path the reconstruction uses, which keeps fixture and target topology
    identical by construction: the Milestone 2 multi-region follow-up target.
    ``ridge_poles`` controls the dihedral: the default is decisively sharp,
    while the soft variant stays just above the segmentation threshold so a
    user may plausibly declare the join smooth.
    """

    degree = 3
    control = 7
    half = 40.0 * scale
    depth = 80.0 * scale
    thickness = 25.0 * scale
    knots = open_uniform_knots(control, degree)
    greville = greville_abscissae(knots, degree)
    # Ridge elevation poles: clamped cubic bowing between elevated endpoints.
    ridge = np.asarray(ridge_poles, dtype=np.float64) * scale

    def roof_poles(side: int, bump: float) -> np.ndarray:
        poles = np.zeros((control, control, 3))
        for i, gu in enumerate(greville):
            for j, gv in enumerate(greville):
                rise = gu if side == 0 else 1.0 - gu
                poles[i, j, 0] = (gu if side == 0 else 1.0 + gu) * half
                poles[i, j, 1] = gv * depth
                # The sine factors vanish on every edge pole row, so the
                # straight outer boundaries and the shared ridge stay exact.
                poles[i, j, 2] = rise * ridge[j] + bump * scale * sin(pi * gu) * sin(pi * gv)
        return poles

    curve_poles = np.column_stack(
        [np.full(control, half), greville * depth, ridge.astype(np.float64)]
    )
    network = SurfaceNetwork(
        units="mm",
        vertices=(
            NetworkVertex("corner-0", np.asarray([0.0, 0.0, 0.0])),
            NetworkVertex("corner-1", np.asarray([2.0 * half, 0.0, 0.0])),
            NetworkVertex("corner-2", np.asarray([2.0 * half, depth, 0.0])),
            NetworkVertex("corner-3", np.asarray([0.0, depth, 0.0])),
            NetworkVertex("crease-0-start", np.asarray([half, 0.0, ridge[0]])),
            NetworkVertex("crease-0-end", np.asarray([half, depth, ridge[-1]])),
        ),
        curves=(
            NetworkCurve(
                id="crease-0",
                degree=degree,
                knots=knots,
                poles=curve_poles,
                start_vertex_id="crease-0-start",
                end_vertex_id="crease-0-end",
                continuity="crease",
            ),
        ),
        patches=(
            NetworkPatch(
                id="patch-0",
                degree=degree,
                knots_u=knots,
                knots_v=knots,
                poles=roof_poles(0, bump=bumps[0]),
                corner_vertex_ids=("corner-0", "crease-0-start", "crease-0-end", "corner-3"),
                shared_boundaries={"u1": "crease-0"},
            ),
            NetworkPatch(
                id="patch-1",
                degree=degree,
                knots_u=knots,
                knots_v=knots,
                poles=roof_poles(1, bump=bumps[1]),
                corner_vertex_ids=("crease-0-start", "corner-1", "corner-2", "crease-0-end"),
                shared_boundaries={"u0": "crease-0"},
            ),
        ),
    )
    payload = {
        "schema": PLATE_ARTIFACT_SCHEMA,
        "units": "mm",
        "network": network.to_artifact(),
        "assembly": {
            "corners": [
                [0.0, 0.0, 0.0],
                [2.0 * half, 0.0, 0.0],
                [2.0 * half, depth, 0.0],
                [0.0, depth, 0.0],
            ],
            "prismVector": [0.0, 0.0, -thickness],
            "sewingToleranceMm": 1e-6,
            "holes": [],
        },
    }
    return rebuild_plate_solid(payload)


def _gable_plate_with_hole(scale: float = 1.0) -> cq.Shape:
    """The sharp gable plate pierced by a vertical cylindrical through hole.

    The hole runs through one roof patch well clear of the ridge and the
    walls: the multi-region-with-holes target mixing two B-spline roofs on a
    shared crease, one cylinder, and five planes in one shell (8 faces).
    """

    plate = _gable_plate_solid(scale=scale)
    cutter = cq.Solid.makeCylinder(
        6.0 * scale,
        80.0 * scale,
        cq.Vector(20.0 * scale, 30.0 * scale, -40.0 * scale),
        cq.Vector(0.0, 0.0, 1.0),
    )
    return plate.cut(cutter)


def _dome_plate_solid(scale: float = 1.0) -> cq.Shape:
    """A gentle freeform plate fused with an exact spherical cap at its apex.

    A ball whose center sits below the freeform top pokes through it, so the
    kernel computes the exact intersection curve and the result carries a true
    sphere face joined to the trimmed B-spline top at a sharp crease rim
    (surface angle at the rim far above the segmentation threshold). The exact
    ground truth is 7 faces: 5 planes, 1 trimmed B-spline, 1 sphere. The dome
    sits at the top's apex where the surface is locally near-planar: that
    keeps the reconstruction's patch/ball intersection a single clean
    transversal curve instead of a wide tangency band.
    """

    degree = 3
    control = 7
    size = 80.0 * scale
    height = 25.0 * scale
    knots = open_uniform_knots(control, degree)
    greville = greville_abscissae(knots, degree)
    poles = np.zeros((control, control, 3))
    for i, gu in enumerate(greville):
        for j, gv in enumerate(greville):
            poles[i, j, 0] = gu * size
            poles[i, j, 1] = gv * size
            interior = 0 < i < control - 1 and 0 < j < control - 1
            if interior:
                # Gentler and symmetric compared to the bump plate: the dome
                # sits at the apex where the top is locally near-planar, so
                # the fitted patch crosses the recognized ball transversally
                # without a wide tangency band.
                poles[i, j, 2] = 2.5 * scale * sin(pi * gu) * sin(pi * gv)
    surface = build_occt_bspline_surface(poles, knots, knots, degree)
    corners = np.asarray([[0.0, 0.0, 0.0], [size, 0.0, 0.0], [size, size, 0.0], [0.0, size, 0.0]])
    plate = assemble_single_patch_plate(
        surface, corners, np.asarray([0.0, 0.0, -height]), sewing_tolerance=1e-6
    )
    # Apex top sits near z ~ 2.1; a 10 mm ball centered 3.6 mm below the
    # rectangle pokes ~4.3 mm proud with a steep rim. The vertical parametric
    # axis keeps the boolean robust (a horizontal seam meridian across the
    # trim curve breaks the fuse against fitted splines); the pole's
    # zero-area triangles are dropped by the canonical tessellation.
    # angleDegrees1=-90 makes the full ball (cadquery's default is a half
    # sphere).
    ball = cq.Solid.makeSphere(
        10.0 * scale,
        cq.Vector(40.0 * scale, 40.0 * scale, -3.6 * scale),
        angleDegrees1=-90,
    )
    return plate.fuse(ball).clean()


def _cone_plate_solid(scale: float = 1.0) -> cq.Shape:
    """A gentle freeform plate fused with an exact conical boss at its apex.

    The cone points away from the plate and extends just below the fitted top,
    so the kernel trims its analytic side against the B-spline along one clean
    transversal loop. The ground truth is 7 faces: 5 planes, 1 trimmed
    B-spline, and 1 cone. As with the spherical cap, the locally near-planar
    apex site avoids a broad near-tangency band and fragmented boolean result.
    """

    degree = 3
    control = 7
    size = 80.0 * scale
    height = 25.0 * scale
    knots = open_uniform_knots(control, degree)
    greville = greville_abscissae(knots, degree)
    poles = np.zeros((control, control, 3))
    for i, gu in enumerate(greville):
        for j, gv in enumerate(greville):
            poles[i, j, 0] = gu * size
            poles[i, j, 1] = gv * size
            interior = 0 < i < control - 1 and 0 < j < control - 1
            if interior:
                poles[i, j, 2] = 2.5 * scale * sin(pi * gu) * sin(pi * gv)
    surface = build_occt_bspline_surface(poles, knots, knots, degree)
    corners = np.asarray([[0.0, 0.0, 0.0], [size, 0.0, 0.0], [size, size, 0.0], [0.0, size, 0.0]])
    plate = assemble_single_patch_plate(
        surface, corners, np.asarray([0.0, 0.0, -height]), sewing_tolerance=1e-6
    )
    # The apex is 12 mm above the boundary rectangle. A 14 mm cone directed
    # downward crosses the top near its locally flat center and terminates
    # inside the plate, leaving only the exact analytic side visible.
    cone_height = 14.0 * scale
    half_angle_deg = 35.0
    base_radius = cone_height * np.tan(np.radians(half_angle_deg))
    cone = cq.Solid.makeCone(
        0.0,
        float(base_radius),
        cone_height,
        cq.Vector(40.0 * scale, 40.0 * scale, 12.0 * scale),
        cq.Vector(0.0, 0.0, -1.0),
    )
    return plate.fuse(cone).clean()


def _torus_bead_plate_solid(scale: float = 1.0) -> cq.Shape:
    """A near-planar freeform plate fused with one exact circular torus bead.

    The torus intersects the top in two closed curves, leaving an outer
    annulus and an inner freeform disk as separate observed regions. A small
    saddle term keeps the inner disk genuinely freeform while the bead site
    remains close to planar. The exact ground truth is eight faces: five
    planes, two trims of one B-spline support, and one torus.
    """

    degree = 3
    control = 7
    size = 80.0 * scale
    height = 25.0 * scale
    knots = open_uniform_knots(control, degree)
    greville = greville_abscissae(knots, degree)
    poles = np.zeros((control, control, 3))
    for i, gu in enumerate(greville):
        for j, gv in enumerate(greville):
            poles[i, j, 0] = gu * size
            poles[i, j, 1] = gv * size
            interior = 0 < i < control - 1 and 0 < j < control - 1
            if interior:
                poles[i, j, 2] = (
                    0.5
                    * scale
                    * (sin(pi * gu) * sin(pi * gv) + sin(2.0 * pi * gu) * sin(2.0 * pi * gv))
                )
    surface = build_occt_bspline_surface(poles, knots, knots, degree)
    corners = np.asarray([[0.0, 0.0, 0.0], [size, 0.0, 0.0], [size, size, 0.0], [0.0, size, 0.0]])
    plate = assemble_single_patch_plate(
        surface, corners, np.asarray([0.0, 0.0, -height]), sewing_tolerance=1e-6
    )
    # The positive vertical axis fixes both torus seam orientations to the
    # empirically stable CadQuery/OCCT placement. Reversing the axis can split
    # the same exposed torus into multiple faces.
    torus = cq.Solid.makeTorus(
        14.0 * scale,
        4.0 * scale,
        cq.Vector(40.0 * scale, 40.0 * scale, -1.35 * scale),
        cq.Vector(0.0, 0.0, 1.0),
    )
    return plate.fuse(torus)


def _bump_plate_with_hole(scale: float = 1.0) -> cq.Shape:
    """The bump plate pierced by a vertical cylindrical through hole.

    The Milestone 3 hybrid target: the exact result mixes one B-spline face
    (with an interior trimming loop), one cylinder, and five planes in a
    single shell.
    """

    plate = _bump_plate_solid(scale=scale)
    cutter = cq.Solid.makeCylinder(
        8.0 * scale,
        60.0 * scale,
        cq.Vector(58.0 * scale, 22.0 * scale, -40.0 * scale),
        cq.Vector(0.0, 0.0, 1.0),
    )
    return plate.cut(cutter)


def _wavy_solid_with_hole(scale: float = 1.0) -> cq.Shape:
    slab = _wavy_bspline_solid(scale=scale)
    cutter = cq.Solid.makeCylinder(
        8.0 * scale,
        60.0 * scale,
        cq.Vector(40.0 * scale, 40.0 * scale, -40.0 * scale),
        cq.Vector(0.0, 0.0, 1.0),
    )
    return slab.cut(cutter)


def _posed_wavy_solid() -> cq.Shape:
    slab = _wavy_bspline_solid()
    rotated = slab.rotate(cq.Vector(0.0, 0.0, 0.0), cq.Vector(1.0, 1.0, 0.0), 30.0)
    return rotated.translate(cq.Vector(25.0, -40.0, 60.0))


def _welded(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Weld shared vertices so noise and manifold checks see one surface."""

    return trimesh.Trimesh(
        vertices=np.asarray(mesh.vertices, dtype=np.float64),
        faces=np.asarray(mesh.faces, dtype=np.int64),
        process=True,
        validate=False,
    )


def _mesh_from_ground_truth(spec: CurvedFixtureSpec, shape: cq.Shape) -> trimesh.Trimesh:
    tessellation = tessellate_shape(
        shape,
        linear_tolerance=spec.linear_tolerance,
        angular_tolerance=spec.angular_tolerance,
    )
    mesh = _welded(
        trimesh.Trimesh(
            vertices=np.asarray(tessellation.vertices, dtype=np.float64),
            faces=np.asarray(tessellation.triangles, dtype=np.int64),
            process=False,
            validate=False,
        )
    )
    if spec.noise_amplitude > 0.0:
        offsets = np.random.RandomState(spec.noise_seed).uniform(
            -spec.noise_amplitude, spec.noise_amplitude, size=len(mesh.vertices)
        )
        vertices = mesh.vertices + mesh.vertex_normals * offsets[:, np.newaxis]
        mesh = trimesh.Trimesh(vertices=vertices, faces=mesh.faces, process=False, validate=False)
    return mesh


def _open_wavy_sheet(grid: int = 24, spacing: float = 3.5) -> trimesh.Trimesh:
    """A wavy height field left open: valid triangles, no enclosed volume."""

    xs = np.arange(grid, dtype=np.float64) * spacing
    ys = np.arange(grid, dtype=np.float64) * spacing
    grid_x, grid_y = np.meshgrid(xs, ys, indexing="ij")
    grid_z = 4.0 * np.sin(grid_x / 12.0) * np.cos(grid_y / 15.0) + 0.05 * grid_x
    vertices = np.column_stack([grid_x.ravel(), grid_y.ravel(), grid_z.ravel()])
    faces: list[tuple[int, int, int]] = []
    for row in range(grid - 1):
        for column in range(grid - 1):
            corner = row * grid + column
            right = corner + grid
            faces.append((corner, right, right + 1))
            faces.append((corner, right + 1, corner + 1))
    return trimesh.Trimesh(
        vertices=vertices,
        faces=np.asarray(faces, dtype=np.int64),
        process=False,
        validate=False,
    )


_BOX_FACES = np.asarray(
    [
        (0, 2, 1),
        (0, 3, 2),
        (4, 5, 6),
        (4, 6, 7),
        (0, 1, 5),
        (0, 5, 4),
        (2, 3, 7),
        (2, 7, 6),
        (0, 4, 7),
        (0, 7, 3),
        (1, 2, 6),
        (1, 6, 5),
    ],
    dtype=np.int64,
)


def _box_vertices(
    minimum: tuple[float, float, float], maximum: tuple[float, float, float]
) -> np.ndarray:
    x0, y0, z0 = minimum
    x1, y1, z1 = maximum
    return np.asarray(
        [
            (x0, y0, z0),
            (x1, y0, z0),
            (x1, y1, z0),
            (x0, y1, z0),
            (x0, y0, z1),
            (x1, y0, z1),
            (x1, y1, z1),
            (x0, y1, z1),
        ],
        dtype=np.float64,
    )


def _boxes_mesh(
    boxes: Sequence[tuple[tuple[float, float, float], tuple[float, float, float]]],
) -> trimesh.Trimesh:
    vertices: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    for index, (minimum, maximum) in enumerate(boxes):
        vertices.append(_box_vertices(minimum, maximum))
        faces.append(_BOX_FACES + 8 * index)
    return trimesh.Trimesh(
        vertices=np.vstack(vertices),
        faces=np.vstack(faces),
        process=False,
        validate=False,
    )


def _non_manifold_fin() -> trimesh.Trimesh:
    """A closed box plus a fin sharing an existing edge: three faces per edge."""

    box = _boxes_mesh([((0.0, 0.0, 0.0), (20.0, 20.0, 20.0))])
    apexes = np.asarray([(0.0, 0.0, 30.0), (20.0, 0.0, 30.0)], dtype=np.float64)
    vertices = np.vstack([box.vertices, apexes])
    fin = np.asarray([(4, 5, 9), (4, 9, 8)], dtype=np.int64)
    return trimesh.Trimesh(
        vertices=vertices,
        faces=np.vstack([box.faces, fin]),
        process=False,
        validate=False,
    )


def _positive_builder(
    factory: Callable[[], cq.Shape],
) -> Callable[[CurvedFixtureSpec], tuple[trimesh.Trimesh, cq.Shape | None]]:
    def build(spec: CurvedFixtureSpec) -> tuple[trimesh.Trimesh, cq.Shape | None]:
        shape = factory()
        return _mesh_from_ground_truth(spec, shape), shape

    return build


def _mesh_builder(
    factory: Callable[[], trimesh.Trimesh],
) -> Callable[[CurvedFixtureSpec], tuple[trimesh.Trimesh, cq.Shape | None]]:
    def build(_: CurvedFixtureSpec) -> tuple[trimesh.Trimesh, cq.Shape | None]:
        return factory(), None

    return build


CURVED_FIXTURE_SPECS: tuple[CurvedFixtureSpec, ...] = (
    CurvedFixtureSpec(
        slug="bspline-bump-plate",
        title="B-spline bump plate",
        category="positive",
        expectation="closed-manifold",
        description=(
            "A plate whose only curved face is one exact bicubic B-spline bump "
            "meeting four planar walls and a planar bottom at straight creases: "
            "the Milestone 1 single-patch reconstruction target."
        ),
        # OCCT deflection is relative to edge size here; 0.002 on 80 mm edges
        # keeps the chordal error near 0.16 mm.
        linear_tolerance=0.002,
        angular_tolerance=0.25,
    ),
    CurvedFixtureSpec(
        slug="bspline-bump-plate-hole",
        title="B-spline bump plate with a through hole",
        category="positive",
        expectation="closed-manifold",
        description=(
            "The bump plate pierced by a vertical 8 mm-radius cylindrical hole: "
            "the Milestone 3 hybrid target mixing a trimmed B-spline face, a "
            "cylinder, and five planes in one shell."
        ),
        linear_tolerance=0.002,
        # Below the 12-degree smooth-region threshold so large boundary fan
        # triangles cannot break off the freeform top.
        angular_tolerance=0.15,
    ),
    CurvedFixtureSpec(
        slug="bspline-dome-plate",
        title="B-spline bump plate with a spherical dome cap",
        category="positive",
        expectation="closed-manifold",
        description=(
            "The bump plate fused with an exact spherical cap poking through "
            "the freeform top at a sharp crease rim: the analytic-cap target "
            "mixing a trimmed B-spline top, a true sphere face, and five "
            "planes in one shell."
        ),
        # The gentle top tessellates coarsely on curvature alone; the finer
        # relative deflection keeps rim-adjacent triangles small enough for a
        # well-conditioned harmonic chart.
        linear_tolerance=0.0008,
        angular_tolerance=0.1,
    ),
    CurvedFixtureSpec(
        slug="bspline-cone-plate",
        title="B-spline bump plate with a conical boss",
        category="positive",
        expectation="closed-manifold",
        description=(
            "The gentle bump plate fused with an exact conical boss at its "
            "locally near-planar apex: the analytic cone-cap target mixing a "
            "trimmed B-spline top, a true cone face, and five planes."
        ),
        # Resolve the apex neighborhood and the sharp cone/freeform trim loop
        # without creating a prohibitively dense benchmark fixture.
        linear_tolerance=0.0008,
        angular_tolerance=0.1,
    ),
    CurvedFixtureSpec(
        slug="bspline-torus-bead-plate",
        title="B-spline plate with a raised torus bead",
        category="positive",
        expectation="closed-manifold",
        description=(
            "A near-planar freeform plate fused with an exact circular torus "
            "bead, leaving outer and inner freeform regions separated by the "
            "recognized analytic ring."
        ),
        linear_tolerance=0.0015,
        angular_tolerance=0.12,
    ),
    CurvedFixtureSpec(
        slug="bspline-gable-plate",
        title="B-spline gable plate with a sharp ridge crease",
        category="positive",
        expectation="closed-manifold",
        description=(
            "A plate whose top is two exact B-spline roof patches meeting at "
            "an elevated, bowed sharp ridge crease: the multi-region crease "
            "network reconstruction target (two freeform regions sharing one "
            "crease curve, pentagon end walls)."
        ),
        linear_tolerance=0.002,
        # Below the 12-degree smooth-region threshold so the gently curved
        # roofs stay single regions while the ridge crease separates them.
        angular_tolerance=0.15,
    ),
    CurvedFixtureSpec(
        slug="bspline-gable-plate-hole",
        title="B-spline gable plate with a through hole",
        category="positive",
        expectation="closed-manifold",
        description=(
            "The sharp gable plate pierced by a vertical 6 mm-radius "
            "cylindrical hole through one roof: the multi-region-with-holes "
            "target mixing two B-spline roofs on a shared crease, one "
            "cylinder, and five planes in one shell."
        ),
        # Finer than the plain gable: the ruled roofs tessellate coarsely on
        # curvature alone, and the hole rim needs small neighbors for a
        # well-conditioned harmonic chart.
        linear_tolerance=0.0008,
        angular_tolerance=0.1,
    ),
    CurvedFixtureSpec(
        slug="bspline-soft-gable-plate",
        title="B-spline gable plate with a soft ridge crease",
        category="positive",
        expectation="closed-manifold",
        description=(
            "The gable plate with a gentle ridge: the dihedral stays just "
            "above the segmentation crease threshold, so the top still "
            "segments into two freeform regions while a user may plausibly "
            "override the detected crease to a smooth join."
        ),
        # The nearly ruled roofs barely trigger curvature-driven subdivision,
        # so a finer relative deflection keeps the source honestly denser
        # than the exact ground truth.
        linear_tolerance=0.0006,
        angular_tolerance=0.1,
    ),
    CurvedFixtureSpec(
        slug="wavy-slab",
        title="Wavy B-spline slab",
        category="positive",
        expectation="closed-manifold",
        description=(
            "Closed solid whose top face is a non-round B-spline sheet meeting "
            "extruded walls at sharp creases, tessellated at standard density."
        ),
    ),
    CurvedFixtureSpec(
        slug="wavy-slab-dense",
        title="Wavy slab, dense tessellation",
        category="positive",
        expectation="closed-manifold",
        description="The same ground truth tessellated an order of magnitude finer.",
        linear_tolerance=0.02,
        angular_tolerance=0.06,
    ),
    CurvedFixtureSpec(
        slug="wavy-slab-noisy",
        title="Wavy slab with vertex noise",
        category="positive",
        expectation="closed-manifold",
        description=(
            "Standard tessellation with deterministic +/-0.03 mm normal-direction "
            "vertex noise, so fitting must approximate instead of interpolate."
        ),
        noise_amplitude=0.03,
        noise_seed=0x4D325043,
    ),
    CurvedFixtureSpec(
        slug="wavy-slab-inch",
        title="Wavy slab in inch units",
        category="positive",
        expectation="closed-manifold",
        description="Physically identical slab expressed in inches (scale 1/25.4).",
        units="in",
        linear_tolerance=0.008,
    ),
    CurvedFixtureSpec(
        slug="wavy-slab-posed",
        title="Wavy slab, rotated and translated",
        category="positive",
        expectation="closed-manifold",
        description="The slab rotated 30 degrees about (1,1,0) and moved off origin.",
    ),
    CurvedFixtureSpec(
        slug="wavy-slab-hole",
        title="Wavy slab with a through hole",
        category="positive",
        expectation="closed-manifold",
        description=(
            "The slab with a vertical 8 mm-radius through hole, adding a "
            "cylindrical face and an interior trimming loop on the B-spline face."
        ),
    ),
    CurvedFixtureSpec(
        slug="wavy-slab-coarse",
        title="Wavy slab, too coarse to fit",
        category="negative",
        expectation="closed-manifold-coarse",
        description=(
            "A valid closed manifold tessellated so coarsely that no unique "
            "smooth surface is justified; reconstruction must report uncertainty."
        ),
        linear_tolerance=2.5,
        angular_tolerance=0.8,
    ),
    CurvedFixtureSpec(
        slug="open-wavy-sheet",
        title="Open wavy sheet",
        category="negative",
        expectation="open-surface",
        description="A wavy height field with boundary edges and no enclosed volume.",
    ),
    CurvedFixtureSpec(
        slug="non-manifold-fin",
        title="Box with a non-manifold fin",
        category="negative",
        expectation="non-manifold",
        description="A closed box plus a fin whose shared edge carries three faces.",
    ),
    CurvedFixtureSpec(
        slug="self-intersecting-boxes",
        title="Two interpenetrating boxes",
        category="negative",
        expectation="self-intersecting",
        description="Two closed shells whose triangles pass through each other.",
    ),
    CurvedFixtureSpec(
        slug="multi-body-boxes",
        title="Two disjoint boxes",
        category="negative",
        expectation="multi-body",
        description="Two disconnected closed bodies in one STL file.",
    ),
)

CURVED_FIXTURES_BY_SLUG: dict[str, CurvedFixtureSpec] = {
    spec.slug: spec for spec in CURVED_FIXTURE_SPECS
}

_BUILDERS: dict[str, Callable[[CurvedFixtureSpec], tuple[trimesh.Trimesh, cq.Shape | None]]] = {
    "bspline-bump-plate": _positive_builder(_bump_plate_solid),
    "bspline-bump-plate-hole": _positive_builder(_bump_plate_with_hole),
    "bspline-dome-plate": _positive_builder(_dome_plate_solid),
    "bspline-cone-plate": _positive_builder(_cone_plate_solid),
    "bspline-torus-bead-plate": _positive_builder(_torus_bead_plate_solid),
    "bspline-gable-plate": _positive_builder(_gable_plate_solid),
    "bspline-gable-plate-hole": _positive_builder(_gable_plate_with_hole),
    # Small bumps: the bump's u-derivative subtracts from the ridge slope, so
    # large interior bumps would flatten the dihedral below the segmentation
    # threshold and merge the two roof regions.
    "bspline-soft-gable-plate": _positive_builder(
        lambda: _gable_plate_solid(
            ridge_poles=(6.5, 6.8, 7.4, 7.0, 7.3, 6.8, 6.5), bumps=(0.5, 0.4)
        )
    ),
    "wavy-slab": _positive_builder(_wavy_bspline_solid),
    "wavy-slab-dense": _positive_builder(_wavy_bspline_solid),
    "wavy-slab-noisy": _positive_builder(_wavy_bspline_solid),
    "wavy-slab-inch": _positive_builder(lambda: _wavy_bspline_solid(scale=1.0 / 25.4)),
    "wavy-slab-posed": _positive_builder(_posed_wavy_solid),
    "wavy-slab-hole": _positive_builder(_wavy_solid_with_hole),
    "wavy-slab-coarse": _positive_builder(_wavy_bspline_solid),
    "open-wavy-sheet": _mesh_builder(_open_wavy_sheet),
    "non-manifold-fin": _mesh_builder(_non_manifold_fin),
    "self-intersecting-boxes": _mesh_builder(
        lambda: _boxes_mesh(
            [
                ((0.0, 0.0, 0.0), (30.0, 30.0, 30.0)),
                ((15.0, 10.0, 5.0), (45.0, 40.0, 35.0)),
            ]
        )
    ),
    "multi-body-boxes": _mesh_builder(
        lambda: _boxes_mesh(
            [
                ((0.0, 0.0, 0.0), (20.0, 20.0, 20.0)),
                ((40.0, 0.0, 0.0), (60.0, 20.0, 20.0)),
            ]
        )
    ),
}


@dataclass(frozen=True, slots=True)
class GeneratedCurvedFixture:
    spec: CurvedFixtureSpec
    # Relative to the corpus root so generated manifests stay byte-identical
    # regardless of where the corpus is written.
    directory: str
    stl_sha256: str
    stl_byte_size: int
    triangle_count: int
    vertex_count: int
    watertight: bool
    winding_consistent: bool
    body_count: int
    ground_truth: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.spec.to_dict(),
            "directory": self.directory,
            "stl": {
                "path": FIXTURE_STL_NAME,
                "sha256": self.stl_sha256,
                "byteSize": self.stl_byte_size,
                "triangleCount": self.triangle_count,
                "vertexCount": self.vertex_count,
            },
            "mesh": {
                "watertight": self.watertight,
                "windingConsistent": self.winding_consistent,
                "bodyCount": self.body_count,
            },
            "groundTruth": self.ground_truth,
        }


def _ground_truth_summary(shape: cq.Shape) -> dict[str, Any]:
    validation = validate_shape(shape, require_tessellation=False)
    bbox = shape.BoundingBox()
    return {
        "volume": validation.volume,
        "area": validation.area,
        "faceCount": validation.face_count,
        "edgeCount": validation.edge_count,
        "faceSurfaces": classify_face_surfaces(shape),
        "boundingBox": [bbox.xmin, bbox.ymin, bbox.zmin, bbox.xmax, bbox.ymax, bbox.zmax],
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate_curved_fixture(
    spec: CurvedFixtureSpec, output_root: str | Path
) -> GeneratedCurvedFixture:
    builder = _BUILDERS[spec.slug]
    mesh, ground_truth_shape = builder(spec)
    directory = Path(output_root) / spec.slug
    directory.mkdir(parents=True, exist_ok=True)
    stl_path = directory / FIXTURE_STL_NAME
    payload = mesh.export(file_type="stl")
    if not isinstance(payload, bytes):
        raise TypeError(f"binary STL export returned {type(payload).__name__}, not bytes")
    stl_path.write_bytes(payload)

    inspection = _welded(mesh)
    generated = GeneratedCurvedFixture(
        spec=spec,
        directory=spec.slug,
        stl_sha256=hashlib.sha256(stl_path.read_bytes()).hexdigest(),
        stl_byte_size=stl_path.stat().st_size,
        triangle_count=len(mesh.faces),
        vertex_count=len(mesh.vertices),
        watertight=bool(inspection.is_watertight),
        winding_consistent=bool(inspection.is_winding_consistent),
        body_count=int(inspection.body_count),
        ground_truth=(
            _ground_truth_summary(ground_truth_shape) if ground_truth_shape is not None else None
        ),
    )
    _write_json(directory / FIXTURE_MANIFEST_NAME, generated.to_dict())
    return generated


def generate_curved_fixture_corpus(
    output_root: str | Path, slugs: Sequence[str] | None = None
) -> list[GeneratedCurvedFixture]:
    selected = CURVED_FIXTURE_SPECS
    if slugs is not None:
        unknown = sorted(set(slugs) - set(CURVED_FIXTURES_BY_SLUG))
        if unknown:
            raise KeyError(f"unknown curved fixture slugs: {', '.join(unknown)}")
        selected = tuple(spec for spec in CURVED_FIXTURE_SPECS if spec.slug in set(slugs))
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    generated = [generate_curved_fixture(spec, root) for spec in selected]
    if slugs is None:
        _write_json(
            root / CORPUS_MANIFEST_NAME,
            {"fixtures": [fixture.to_dict() for fixture in generated]},
        )
    return generated


__all__ = [
    "CORPUS_MANIFEST_NAME",
    "CURVED_FIXTURES_BY_SLUG",
    "CURVED_FIXTURE_SPECS",
    "FIXTURE_MANIFEST_NAME",
    "FIXTURE_STL_NAME",
    "CurvedFixtureSpec",
    "GeneratedCurvedFixture",
    "generate_curved_fixture",
    "generate_curved_fixture_corpus",
]
