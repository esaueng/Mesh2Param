"""Sparse tensor-product B-spline fitting for one freeform chart (Milestone 1).

Fits a clamped, non-rational, open-uniform tensor-product B-spline surface to
parameterized scatter samples by weighted sparse least squares with a
control-net fairness term, optional fixed boundary poles, Huber IRLS robust
reweighting, Gauss-Newton UV reprojection, and uniform span refinement under a
hard budget. Everything is deterministic: no randomness, ordering-stable
sparse assembly, and direct sparse factorization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from OCP.Geom import Geom_BSplineSurface
from OCP.gp import gp_Pnt
from OCP.TColgp import TColgp_Array2OfPnt
from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
from scipy.sparse import coo_matrix, csr_matrix, vstack
from scipy.sparse.linalg import splu


def open_uniform_knots(control_count: int, degree: int) -> np.ndarray:
    """Clamped open-uniform knot vector on [0, 1] for ``control_count`` poles."""

    if control_count <= degree:
        raise ValueError("control count must exceed the degree")
    spans = control_count - degree
    interior = np.arange(1, spans) / spans
    return np.concatenate([np.zeros(degree + 1), interior, np.ones(degree + 1)])


def greville_abscissae(knots: np.ndarray, degree: int) -> np.ndarray:
    """Greville parameter of every pole: mean of ``degree`` consecutive knots."""

    control_count = len(knots) - degree - 1
    return np.asarray([knots[i + 1 : i + degree + 1].mean() for i in range(control_count)])


def _basis_windows(
    parameters: np.ndarray, knots: np.ndarray, degree: int
) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized Cox-de Boor: spans and the ``degree + 1`` local basis values."""

    control_count = len(knots) - degree - 1
    x = np.clip(np.asarray(parameters, dtype=np.float64), 0.0, 1.0)
    spans = np.searchsorted(knots, x, side="right") - 1
    spans = np.clip(spans, degree, control_count - 1)
    count = len(x)
    values = np.zeros((count, degree + 1))
    values[:, 0] = 1.0
    left = np.zeros((count, degree + 1))
    right = np.zeros((count, degree + 1))
    for level in range(1, degree + 1):
        left[:, level] = x - knots[spans + 1 - level]
        right[:, level] = knots[spans + level] - x
        saved = np.zeros(count)
        for r in range(level):
            denominator = right[:, r + 1] + left[:, level - r]
            safe = np.where(denominator == 0.0, 1.0, denominator)
            term = np.where(denominator == 0.0, 0.0, values[:, r] / safe)
            values[:, r] = saved + right[:, r + 1] * term
            saved = left[:, level - r] * term
        values[:, level] = saved
    return spans, values


def _basis_windows_with_derivative(
    parameters: np.ndarray, knots: np.ndarray, degree: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Spans, basis values, and first-derivative values in the local window."""

    spans, values = _basis_windows(parameters, knots, degree)
    count = len(parameters)
    if degree == 0:
        return spans, values, np.zeros_like(values)
    _, lower = _basis_windows(parameters, knots[1:-1], degree - 1)
    # The degree-1 window evaluated on the reduced knot vector aligns with
    # local pole offsets 0..degree-1 of the same span.
    derivatives = np.zeros((count, degree + 1))
    starts = spans - degree
    for offset in range(degree + 1):
        pole = starts + offset
        left_den = knots[pole + degree] - knots[pole]
        right_den = knots[pole + degree + 1] - knots[pole + 1]
        left_term = np.where(
            (offset > 0) & (left_den != 0.0),
            lower[:, max(offset - 1, 0)] / np.where(left_den == 0.0, 1.0, left_den),
            0.0,
        )
        right_term = np.where(
            (offset < degree) & (right_den != 0.0),
            lower[:, min(offset, degree - 1)] / np.where(right_den == 0.0, 1.0, right_den),
            0.0,
        )
        derivatives[:, offset] = degree * (left_term - right_term)
    return spans, values, derivatives


def tensor_design_matrix(
    uv: np.ndarray,
    knots_u: np.ndarray,
    knots_v: np.ndarray,
    degree: int,
) -> csr_matrix:
    """Sparse design matrix mapping the flattened pole grid to sample points."""

    control_u = len(knots_u) - degree - 1
    control_v = len(knots_v) - degree - 1
    spans_u, windows_u = _basis_windows(uv[:, 0], knots_u, degree)
    spans_v, windows_v = _basis_windows(uv[:, 1], knots_v, degree)
    window = degree + 1
    count = len(uv)
    rows = np.repeat(np.arange(count), window * window)
    offset_u = np.arange(window)
    offset_v = np.arange(window)
    pole_u = (spans_u - degree)[:, None, None] + offset_u[None, :, None]
    pole_v = (spans_v - degree)[:, None, None] + offset_v[None, None, :]
    columns = (pole_u * control_v + pole_v).reshape(-1)
    data = (windows_u[:, :, None] * windows_v[:, None, :]).reshape(-1)
    return coo_matrix((data, (rows, columns)), shape=(count, control_u * control_v)).tocsr()


def _second_difference_operator(control_u: int, control_v: int) -> csr_matrix:
    """Second differences of the pole grid along both directions."""

    blocks: list[csr_matrix] = []
    index = np.arange(control_u * control_v).reshape(control_u, control_v)
    if control_u > 2:
        rows_count = (control_u - 2) * control_v
        rows = np.repeat(np.arange(rows_count), 3)
        base = index[: control_u - 2, :].reshape(-1)
        columns = np.stack([base, base + control_v, base + 2 * control_v], axis=1).reshape(-1)
        data = np.tile([1.0, -2.0, 1.0], rows_count)
        blocks.append(
            coo_matrix((data, (rows, columns)), shape=(rows_count, control_u * control_v)).tocsr()
        )
    if control_v > 2:
        rows_count = control_u * (control_v - 2)
        rows = np.repeat(np.arange(rows_count), 3)
        base = index[:, : control_v - 2].reshape(-1)
        columns = np.stack([base, base + 1, base + 2], axis=1).reshape(-1)
        data = np.tile([1.0, -2.0, 1.0], rows_count)
        blocks.append(
            coo_matrix((data, (rows, columns)), shape=(rows_count, control_u * control_v)).tocsr()
        )
    if not blocks:
        return csr_matrix((0, control_u * control_v))
    return vstack(blocks).tocsr()


def rectangle_boundary_poles(
    corners: np.ndarray,
    greville_u: np.ndarray,
    greville_v: np.ndarray,
) -> dict[tuple[int, int], np.ndarray]:
    """Boundary pole positions for an exactly straight rectangle boundary.

    Collinear boundary poles make every natural boundary curve geometrically
    identical to its corner-to-corner segment, so planar neighbor faces built
    from the same corners share the boundary exactly.
    """

    if corners.shape != (4, 3):
        raise ValueError("rectangle boundary needs exactly four 3-D corners")
    control_u = len(greville_u)
    control_v = len(greville_v)
    c0, c1, c2, c3 = corners
    poles: dict[tuple[int, int], np.ndarray] = {}
    for i, s in enumerate(greville_u):
        poles[(i, 0)] = c0 + s * (c1 - c0)
        poles[(i, control_v - 1)] = c3 + s * (c2 - c3)
    for j, s in enumerate(greville_v):
        poles[(0, j)] = c0 + s * (c3 - c0)
        poles[(control_u - 1, j)] = c1 + s * (c2 - c1)
    return poles


@dataclass(frozen=True, slots=True)
class FitIteration:
    spans_u: int
    spans_v: int
    rms_distance: float
    p95_distance: float
    maximum_distance: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "spansU": self.spans_u,
            "spansV": self.spans_v,
            "rmsDistance": self.rms_distance,
            "p95Distance": self.p95_distance,
            "maximumDistance": self.maximum_distance,
        }


@dataclass(frozen=True, slots=True)
class FittedPatch:
    poles: np.ndarray = field(repr=False)
    degree: int
    knots_u: np.ndarray = field(repr=False)
    knots_v: np.ndarray = field(repr=False)
    rms_distance: float
    p95_distance: float
    maximum_distance: float
    iterations: tuple[FitIteration, ...]
    converged: bool

    @property
    def control_u(self) -> int:
        return int(self.poles.shape[0])

    @property
    def control_v(self) -> int:
        return int(self.poles.shape[1])

    def evaluate(self, uv: np.ndarray) -> np.ndarray:
        design = tensor_design_matrix(uv, self.knots_u, self.knots_v, self.degree)
        flat = self.poles.reshape(-1, 3)
        return np.asarray(design @ flat)

    def to_occt_surface(self) -> Geom_BSplineSurface:
        return build_occt_bspline_surface(self.poles, self.knots_u, self.knots_v, self.degree)

    def to_dict(self) -> dict[str, Any]:
        return {
            "degree": self.degree,
            "controlU": self.control_u,
            "controlV": self.control_v,
            "rmsDistance": self.rms_distance,
            "p95Distance": self.p95_distance,
            "maximumDistance": self.maximum_distance,
            "converged": self.converged,
            "iterations": [iteration.to_dict() for iteration in self.iterations],
        }


def _unique_knots(knots: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    values, counts = np.unique(np.round(knots, 12), return_counts=True)
    return values, counts


def build_occt_bspline_surface(
    poles: np.ndarray,
    knots_u: np.ndarray,
    knots_v: np.ndarray,
    degree: int,
) -> Geom_BSplineSurface:
    control_u, control_v, _ = poles.shape
    array = TColgp_Array2OfPnt(1, control_u, 1, control_v)
    for i in range(control_u):
        for j in range(control_v):
            x, y, z = poles[i, j]
            array.SetValue(i + 1, j + 1, gp_Pnt(float(x), float(y), float(z)))
    unique_u, mult_u = _unique_knots(knots_u)
    unique_v, mult_v = _unique_knots(knots_v)
    occt_knots_u = TColStd_Array1OfReal(1, len(unique_u))
    occt_mults_u = TColStd_Array1OfInteger(1, len(unique_u))
    for index, (value, count) in enumerate(zip(unique_u, mult_u, strict=True), start=1):
        occt_knots_u.SetValue(index, float(value))
        occt_mults_u.SetValue(index, int(count))
    occt_knots_v = TColStd_Array1OfReal(1, len(unique_v))
    occt_mults_v = TColStd_Array1OfInteger(1, len(unique_v))
    for index, (value, count) in enumerate(zip(unique_v, mult_v, strict=True), start=1):
        occt_knots_v.SetValue(index, float(value))
        occt_mults_v.SetValue(index, int(count))
    return Geom_BSplineSurface(
        array, occt_knots_u, occt_knots_v, occt_mults_u, occt_mults_v, degree, degree
    )


def _solve_patch(
    uv: np.ndarray,
    points: np.ndarray,
    weights: np.ndarray,
    knots_u: np.ndarray,
    knots_v: np.ndarray,
    degree: int,
    fairness: float,
    fixed_poles: dict[tuple[int, int], np.ndarray] | None,
) -> np.ndarray:
    control_u = len(knots_u) - degree - 1
    control_v = len(knots_v) - degree - 1
    total = control_u * control_v
    design = tensor_design_matrix(uv, knots_u, knots_v, degree)
    smoothing = _second_difference_operator(control_u, control_v)

    fixed_values = np.zeros((total, 3))
    fixed_mask = np.zeros(total, dtype=bool)
    if fixed_poles:
        for (i, j), value in fixed_poles.items():
            flat = i * control_v + j
            fixed_mask[flat] = True
            fixed_values[flat] = value
    free = np.flatnonzero(~fixed_mask)
    if len(free) == 0:
        return fixed_values.reshape(control_u, control_v, 3)

    weight_diag = np.asarray(weights, dtype=np.float64)
    design_weighted = design.multiply(weight_diag[:, None]).tocsr()
    design_free = design[:, free]
    design_fixed = design[:, fixed_mask]
    smoothing_free = smoothing[:, free]
    smoothing_fixed = smoothing[:, fixed_mask]

    normal = (design_weighted[:, free].T @ design_free) + fairness * (
        smoothing_free.T @ smoothing_free
    )
    target = points - design_fixed @ fixed_values[fixed_mask]
    rhs = design_weighted[:, free].T @ target - fairness * (
        smoothing_free.T @ (smoothing_fixed @ fixed_values[fixed_mask])
    )
    solved = splu(normal.tocsc()).solve(np.asarray(rhs))

    flat_poles = fixed_values.copy()
    flat_poles[free] = solved
    return flat_poles.reshape(control_u, control_v, 3)


def _reproject_uv(
    uv: np.ndarray,
    points: np.ndarray,
    poles: np.ndarray,
    knots_u: np.ndarray,
    knots_v: np.ndarray,
    degree: int,
    steps: int = 2,
) -> np.ndarray:
    """Gauss-Newton closest-point update of the sample parameters."""

    control_v = poles.shape[1]
    flat = poles.reshape(-1, 3)
    current = uv.copy()
    for _ in range(steps):
        spans_u, basis_u, derivative_u = _basis_windows_with_derivative(
            current[:, 0], knots_u, degree
        )
        spans_v, basis_v, derivative_v = _basis_windows_with_derivative(
            current[:, 1], knots_v, degree
        )
        window = degree + 1
        offsets = np.arange(window)
        pole_u = (spans_u - degree)[:, None, None] + offsets[None, :, None]
        pole_v = (spans_v - degree)[:, None, None] + offsets[None, None, :]
        indices = pole_u * control_v + pole_v
        local = flat[indices]  # (n, window, window, 3)
        weight_s = basis_u[:, :, None] * basis_v[:, None, :]
        weight_du = derivative_u[:, :, None] * basis_v[:, None, :]
        weight_dv = basis_u[:, :, None] * derivative_v[:, None, :]
        surface = np.einsum("nab,nabk->nk", weight_s, local)
        tangent_u = np.einsum("nab,nabk->nk", weight_du, local)
        tangent_v = np.einsum("nab,nabk->nk", weight_dv, local)
        residual = surface - points
        a11 = np.einsum("nk,nk->n", tangent_u, tangent_u)
        a12 = np.einsum("nk,nk->n", tangent_u, tangent_v)
        a22 = np.einsum("nk,nk->n", tangent_v, tangent_v)
        b1 = -np.einsum("nk,nk->n", tangent_u, residual)
        b2 = -np.einsum("nk,nk->n", tangent_v, residual)
        determinant = a11 * a22 - a12 * a12
        safe = np.where(np.abs(determinant) < 1e-18, 1.0, determinant)
        du = np.where(np.abs(determinant) < 1e-18, 0.0, (b1 * a22 - b2 * a12) / safe)
        dv = np.where(np.abs(determinant) < 1e-18, 0.0, (b2 * a11 - b1 * a12) / safe)
        current = np.clip(
            current + np.stack([du, dv], axis=1),
            0.0,
            1.0,
        )
    return current


def _distances(
    uv: np.ndarray,
    points: np.ndarray,
    poles: np.ndarray,
    knots_u: np.ndarray,
    knots_v: np.ndarray,
    degree: int,
) -> np.ndarray:
    design = tensor_design_matrix(uv, knots_u, knots_v, degree)
    surface = design @ poles.reshape(-1, 3)
    return np.asarray(np.linalg.norm(np.asarray(surface) - points, axis=1))


def _huber_weights(distances: np.ndarray) -> np.ndarray:
    scale = 1.4826 * float(np.median(distances))
    if scale <= 0.0:
        return np.ones_like(distances)
    threshold = 2.5 * scale
    with np.errstate(divide="ignore"):
        ratio = np.where(distances > threshold, threshold / distances, 1.0)
    return ratio


@dataclass(frozen=True, slots=True)
class SurfaceFitSettings:
    degree: int = 3
    initial_spans: int = 4
    maximum_spans: int = 32
    maximum_refinements: int = 4
    fairness: float = 1e-3
    robust_reweighting_rounds: int = 1
    reprojection_steps: int = 2

    def validate(self) -> None:
        if self.degree < 2:
            raise ValueError("surface degree must be at least 2")
        if self.initial_spans < 1 or self.maximum_spans < self.initial_spans:
            raise ValueError("span budget must satisfy 1 <= initial <= maximum")
        if self.maximum_refinements < 0 or self.robust_reweighting_rounds < 0:
            raise ValueError("iteration budgets must be non-negative")
        if self.fairness < 0.0:
            raise ValueError("fairness must be non-negative")


def fit_bspline_patch(
    uv: np.ndarray,
    points: np.ndarray,
    weights: np.ndarray,
    tolerance: float,
    *,
    settings: SurfaceFitSettings | None = None,
    rectangle_corners: np.ndarray | None = None,
) -> FittedPatch:
    """Fit one clamped tensor-product patch, refining spans until tolerance.

    ``rectangle_corners`` (4x3), when given, pins every boundary pole to the
    exact corner-to-corner segments so the fitted patch's natural boundary is
    straight and shareable with planar neighbor faces.
    """

    settings = settings or SurfaceFitSettings()
    settings.validate()
    uv = np.asarray(uv, dtype=np.float64)
    points = np.asarray(points, dtype=np.float64)
    base_weights = np.asarray(weights, dtype=np.float64)
    if len(uv) != len(points) or len(points) != len(base_weights):
        raise ValueError("uv, points, and weights must have matching lengths")
    if np.any(base_weights <= 0.0) or not np.all(np.isfinite(base_weights)):
        raise ValueError("sample weights must be positive and finite")
    if tolerance <= 0.0:
        raise ValueError("fit tolerance must be positive")
    base_weights = base_weights / base_weights.mean()

    # Keep the least-squares system overdetermined: more than two samples per
    # control point, or empty knot spans leave the normal matrix near-singular
    # and the free poles unbounded.
    sample_span_cap = max(1, int(np.sqrt(len(points) / 2.0)) - settings.degree)
    maximum_spans = max(settings.initial_spans, min(settings.maximum_spans, sample_span_cap))

    spans = settings.initial_spans
    iterations: list[FitIteration] = []
    best: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None = None
    for _ in range(settings.maximum_refinements + 1):
        control = spans + settings.degree
        knots_u = open_uniform_knots(control, settings.degree)
        knots_v = open_uniform_knots(control, settings.degree)
        fixed_poles: dict[tuple[int, int], np.ndarray] | None = None
        if rectangle_corners is not None:
            fixed_poles = rectangle_boundary_poles(
                np.asarray(rectangle_corners, dtype=np.float64),
                greville_abscissae(knots_u, settings.degree),
                greville_abscissae(knots_v, settings.degree),
            )
        current_uv = uv
        sample_weights = base_weights
        poles = _solve_patch(
            current_uv,
            points,
            sample_weights,
            knots_u,
            knots_v,
            settings.degree,
            settings.fairness,
            fixed_poles,
        )
        for _ in range(settings.robust_reweighting_rounds):
            current_uv = _reproject_uv(
                current_uv,
                points,
                poles,
                knots_u,
                knots_v,
                settings.degree,
                steps=settings.reprojection_steps,
            )
            residuals = _distances(current_uv, points, poles, knots_u, knots_v, settings.degree)
            sample_weights = base_weights * _huber_weights(residuals)
            sample_weights = sample_weights / sample_weights.mean()
            poles = _solve_patch(
                current_uv,
                points,
                sample_weights,
                knots_u,
                knots_v,
                settings.degree,
                settings.fairness,
                fixed_poles,
            )
        current_uv = _reproject_uv(
            current_uv,
            points,
            poles,
            knots_u,
            knots_v,
            settings.degree,
            steps=settings.reprojection_steps,
        )
        residuals = _distances(current_uv, points, poles, knots_u, knots_v, settings.degree)
        iterations.append(
            FitIteration(
                spans_u=spans,
                spans_v=spans,
                rms_distance=float(np.sqrt(np.mean(residuals**2))),
                p95_distance=float(np.percentile(residuals, 95)),
                maximum_distance=float(residuals.max()),
            )
        )
        best = (poles, knots_u, knots_v, current_uv, residuals)
        if residuals.max() <= tolerance:
            break
        if spans >= maximum_spans:
            break
        spans = min(spans * 2, maximum_spans)

    assert best is not None
    poles, knots_u, knots_v, _, residuals = best
    return FittedPatch(
        poles=poles,
        degree=settings.degree,
        knots_u=knots_u,
        knots_v=knots_v,
        rms_distance=float(np.sqrt(np.mean(residuals**2))),
        p95_distance=float(np.percentile(residuals, 95)),
        maximum_distance=float(residuals.max()),
        iterations=tuple(iterations),
        converged=bool(residuals.max() <= tolerance),
    )


def curve_design_matrix(parameters: np.ndarray, knots: np.ndarray, degree: int) -> csr_matrix:
    """Sparse design matrix mapping curve poles to sample points."""

    control = len(knots) - degree - 1
    spans, windows = _basis_windows(parameters, knots, degree)
    window = degree + 1
    count = len(parameters)
    rows = np.repeat(np.arange(count), window)
    columns = ((spans - degree)[:, None] + np.arange(window)[None, :]).reshape(-1)
    return coo_matrix((windows.reshape(-1), (rows, columns)), shape=(count, control)).tocsr()


def fit_bspline_curve(
    parameters: np.ndarray,
    points: np.ndarray,
    knots: np.ndarray,
    degree: int,
    *,
    fairness: float = 1e-3,
    fixed_endpoints: tuple[np.ndarray, np.ndarray] | None = None,
) -> np.ndarray:
    """Least-squares cubic curve fit with fairness and pinned endpoints.

    The knot vector is supplied by the caller so a shared boundary curve can
    use exactly the knots of the surface direction it will bound; its poles
    then double as the surfaces' shared boundary pole rows.
    """

    control = len(knots) - degree - 1
    design = curve_design_matrix(np.asarray(parameters, dtype=np.float64), knots, degree)
    smoothing_rows = control - 2
    if smoothing_rows > 0:
        base = np.arange(smoothing_rows)
        smoothing = coo_matrix(
            (
                np.tile([1.0, -2.0, 1.0], smoothing_rows),
                (np.repeat(base, 3), np.stack([base, base + 1, base + 2], axis=1).reshape(-1)),
            ),
            shape=(smoothing_rows, control),
        ).tocsr()
    else:
        smoothing = csr_matrix((0, control))

    fixed_mask = np.zeros(control, dtype=bool)
    fixed_values = np.zeros((control, 3))
    if fixed_endpoints is not None:
        fixed_mask[0] = True
        fixed_mask[-1] = True
        fixed_values[0] = fixed_endpoints[0]
        fixed_values[-1] = fixed_endpoints[1]
    free = np.flatnonzero(~fixed_mask)
    if len(free) == 0:
        return fixed_values

    normal = (design[:, free].T @ design[:, free]) + fairness * (
        smoothing[:, free].T @ smoothing[:, free]
    )
    target = np.asarray(points, dtype=np.float64) - design[:, fixed_mask] @ fixed_values[fixed_mask]
    rhs = design[:, free].T @ target - fairness * (
        smoothing[:, free].T @ (smoothing[:, fixed_mask] @ fixed_values[fixed_mask])
    )
    poles = fixed_values.copy()
    poles[free] = splu(normal.tocsc()).solve(np.asarray(rhs))
    return poles


@dataclass(frozen=True, slots=True)
class PatchSystem:
    """One chart's samples and pinned poles inside a joint network solve."""

    uv: np.ndarray = field(repr=False)
    points: np.ndarray = field(repr=False)
    weights: np.ndarray = field(repr=False)
    fixed_poles: dict[tuple[int, int], np.ndarray] = field(repr=False)


@dataclass(frozen=True, slots=True)
class PoleConstraint:
    """Quadratic penalty ``|| sum coeff * P[patch][pole] - target ||^2``.

    The C1 (hence G1) coupling across an artificial smooth boundary is the row
    ``P_a[n-2, j] + P_b[1, j] - 2 * S_j = 0`` where ``S_j`` is the shared
    boundary pole -- itself an unknown when the boundary is aliased.
    """

    entries: tuple[tuple[int, tuple[int, int], float], ...]
    target: np.ndarray = field(repr=False)


PoleSlot = tuple[int, tuple[int, int]]


def solve_patch_network(
    systems: list[PatchSystem],
    knots_u: np.ndarray,
    knots_v: np.ndarray,
    degree: int,
    *,
    fairness: float = 1e-3,
    shared_poles: list[tuple[PoleSlot, PoleSlot]] | None = None,
    constraints: list[PoleConstraint] | None = None,
    constraint_weight: float = 10.0,
) -> list[np.ndarray]:
    """Solve every patch's poles jointly with shared boundaries as one unknown.

    ``shared_poles`` aliases pole slots across patches into a single unknown
    (true common topology: both boundary rows ARE the same curve poles), and
    ``constraints`` adds weighted linear penalty rows such as C1 couplings.
    """

    control_u = len(knots_u) - degree - 1
    control_v = len(knots_v) - degree - 1
    total = control_u * control_v
    patch_count = len(systems)

    def slot(patch: int, pole: tuple[int, int]) -> int:
        return patch * total + pole[0] * control_v + pole[1]

    # Union-find over pole slots so aliased boundary poles are one unknown.
    parents = np.arange(patch_count * total)

    def find(node: int) -> int:
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = int(parents[node])
        return node

    for slot_a, slot_b in shared_poles or []:
        root_a, root_b = find(slot(*slot_a)), find(slot(*slot_b))
        if root_a != root_b:
            parents[max(root_a, root_b)] = min(root_a, root_b)

    fixed_class_values: dict[int, np.ndarray] = {}
    for index, system in enumerate(systems):
        for pole, value in system.fixed_poles.items():
            root = find(slot(index, pole))
            value = np.asarray(value, dtype=np.float64)
            existing = fixed_class_values.get(root)
            if existing is not None and not np.allclose(existing, value, atol=1e-9):
                raise ValueError(
                    "aliased poles are pinned to conflicting positions; the shared "
                    "boundary cannot satisfy both patches"
                )
            fixed_class_values[root] = value

    roots = np.asarray([find(node) for node in range(patch_count * total)])
    free_roots = sorted(set(int(root) for root in roots) - set(fixed_class_values))
    column_of_root = {root: column for column, root in enumerate(free_roots)}
    unknowns = len(free_roots)

    fixed_masks: list[np.ndarray] = []
    fixed_values: list[np.ndarray] = []
    for index in range(patch_count):
        patch_roots = roots[index * total : (index + 1) * total]
        mask = np.asarray([root in fixed_class_values for root in patch_roots])
        values = np.zeros((total, 3))
        for flat, root in enumerate(patch_roots):
            if root in fixed_class_values:
                values[flat] = fixed_class_values[root]
        fixed_masks.append(mask)
        fixed_values.append(values)
    if unknowns == 0:
        return [values.reshape(control_u, control_v, 3) for values in fixed_values]

    normal = csr_matrix((unknowns, unknowns))
    rhs = np.zeros((unknowns, 3))
    smoothing = _second_difference_operator(control_u, control_v)
    for index, system in enumerate(systems):
        mask = fixed_masks[index]
        values = fixed_values[index]
        patch_roots = roots[index * total : (index + 1) * total]
        free_flats = np.flatnonzero(~mask)
        # Expansion mapping this patch's free pole slots to global class
        # columns; aliased slots in different patches share a column.
        expand = coo_matrix(
            (
                np.ones(len(free_flats)),
                (
                    free_flats,
                    np.asarray([column_of_root[int(patch_roots[flat])] for flat in free_flats]),
                ),
            ),
            shape=(total, unknowns),
        ).tocsr()
        design = tensor_design_matrix(
            np.asarray(system.uv, dtype=np.float64), knots_u, knots_v, degree
        )
        weights = np.asarray(system.weights, dtype=np.float64)
        design_weighted = design.multiply(weights[:, None]).tocsr()
        design_global = design @ expand
        design_weighted_global = design_weighted @ expand
        smoothing_global = smoothing @ expand
        target = np.asarray(system.points, dtype=np.float64) - design[:, mask] @ values[mask]
        normal = (
            normal
            + design_weighted_global.T @ design_global
            + fairness * (smoothing_global.T @ smoothing_global)
        )
        rhs += np.asarray(design_weighted_global.T @ target) - fairness * np.asarray(
            smoothing_global.T @ (smoothing[:, mask] @ values[mask])
        )

    for constraint in constraints or []:
        column_coefficients: dict[int, float] = {}
        constant = np.asarray(constraint.target, dtype=np.float64).copy()
        for patch, pole, coefficient in constraint.entries:
            root = find(slot(patch, pole))
            if root in fixed_class_values:
                constant -= coefficient * fixed_class_values[root]
            else:
                column = column_of_root[root]
                column_coefficients[column] = column_coefficients.get(column, 0.0) + coefficient
        if not column_coefficients:
            continue
        columns = np.asarray(sorted(column_coefficients), dtype=np.int64)
        coefficients = np.asarray([column_coefficients[int(c)] for c in columns])
        row_matrix = coo_matrix(
            (coefficients, (np.zeros(len(columns), dtype=np.int64), columns)),
            shape=(1, unknowns),
        ).tocsr()
        normal = normal + constraint_weight * (row_matrix.T @ row_matrix)
        rhs += constraint_weight * np.asarray(row_matrix.T @ constant[None, :])

    solution = splu(normal.tocsc()).solve(rhs)
    results: list[np.ndarray] = []
    for index in range(patch_count):
        patch_roots = roots[index * total : (index + 1) * total]
        values = fixed_values[index].copy()
        for flat, root in enumerate(patch_roots):
            if root not in fixed_class_values:
                values[flat] = solution[column_of_root[int(root)]]
        results.append(values.reshape(control_u, control_v, 3))
    return results


def reproject_patch_uv(
    uv: np.ndarray,
    points: np.ndarray,
    poles: np.ndarray,
    knots_u: np.ndarray,
    knots_v: np.ndarray,
    degree: int,
    *,
    steps: int = 2,
) -> np.ndarray:
    """Public Gauss-Newton closest-point parameter update."""

    return _reproject_uv(uv, points, poles, knots_u, knots_v, degree, steps=steps)


def patch_distances(
    uv: np.ndarray,
    points: np.ndarray,
    poles: np.ndarray,
    knots_u: np.ndarray,
    knots_v: np.ndarray,
    degree: int,
) -> np.ndarray:
    """Distances from samples to the patch at their current parameters."""

    return _distances(uv, points, poles, knots_u, knots_v, degree)


__all__ = [
    "FitIteration",
    "FittedPatch",
    "PatchSystem",
    "PoleConstraint",
    "PoleSlot",
    "SurfaceFitSettings",
    "build_occt_bspline_surface",
    "curve_design_matrix",
    "fit_bspline_curve",
    "fit_bspline_patch",
    "greville_abscissae",
    "open_uniform_knots",
    "patch_distances",
    "rectangle_boundary_poles",
    "reproject_patch_uv",
    "solve_patch_network",
    "tensor_design_matrix",
]
