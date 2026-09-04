//! The small amount of linear algebra the fits need: a 3-vector, a symmetric
//! 3x3 Jacobi eigen-decomposition, and a dense solve for `n <= 4`.
//!
//! Local on purpose. The kernel's own vector types travel with the kernel pin,
//! and a fit that changed meaning when the pin moved would make the corpus
//! scoreboard unreadable.

/// A 3-vector in the mesh's own units.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct V3 {
    /// x component.
    pub x: f64,
    /// y component.
    pub y: f64,
    /// z component.
    pub z: f64,
}

impl V3 {
    /// The zero vector.
    pub const ZERO: Self = Self::new(0.0, 0.0, 0.0);

    /// A vector from its components.
    pub const fn new(x: f64, y: f64, z: f64) -> Self {
        Self { x, y, z }
    }

    /// A vector from an array.
    pub const fn from_arr(a: [f64; 3]) -> Self {
        Self::new(a[0], a[1], a[2])
    }

    /// The components as an array.
    pub const fn arr(self) -> [f64; 3] {
        [self.x, self.y, self.z]
    }

    /// Component-wise sum.
    pub fn add(self, o: Self) -> Self {
        Self::new(self.x + o.x, self.y + o.y, self.z + o.z)
    }

    /// Component-wise difference.
    pub fn sub(self, o: Self) -> Self {
        Self::new(self.x - o.x, self.y - o.y, self.z - o.z)
    }

    /// Scalar multiple.
    pub fn mul(self, s: f64) -> Self {
        Self::new(self.x * s, self.y * s, self.z * s)
    }

    /// Dot product.
    pub fn dot(self, o: Self) -> f64 {
        self.x.mul_add(o.x, self.y.mul_add(o.y, self.z * o.z))
    }

    /// Cross product.
    pub fn cross(self, o: Self) -> Self {
        Self::new(
            self.y.mul_add(o.z, -(self.z * o.y)),
            self.z.mul_add(o.x, -(self.x * o.z)),
            self.x.mul_add(o.y, -(self.y * o.x)),
        )
    }

    /// Euclidean length.
    pub fn norm(self) -> f64 {
        self.dot(self).sqrt()
    }

    /// The unit vector in this direction, or `None` when the vector is too
    /// short to carry a meaningful direction.
    pub fn unit(self) -> Option<Self> {
        let n = self.norm();
        if n > 1e-300 {
            Some(self.mul(1.0 / n))
        } else {
            None
        }
    }

    /// The component of `self` perpendicular to the unit direction `d`.
    pub fn reject(self, d: Self) -> Self {
        self.sub(d.mul(self.dot(d)))
    }
}

/// Angle between two directions, in radians, robust at the clamp ends.
pub fn angle_between(a: V3, b: V3) -> f64 {
    match (a.unit(), b.unit()) {
        (Some(u), Some(v)) => u.dot(v).clamp(-1.0, 1.0).acos(),
        _ => 0.0,
    }
}

/// Angle between two lines — directions taken up to sign — in radians.
pub fn angle_undirected(a: V3, b: V3) -> f64 {
    match (a.unit(), b.unit()) {
        (Some(u), Some(v)) => u.dot(v).abs().clamp(-1.0, 1.0).acos(),
        _ => 0.0,
    }
}

/// Some unit vector perpendicular to `d`.
pub fn perp(d: V3) -> V3 {
    let seed = if d.x.abs() < 0.9 {
        V3::new(1.0, 0.0, 0.0)
    } else {
        V3::new(0.0, 1.0, 0.0)
    };
    d.cross(seed).unit().unwrap_or(V3::new(0.0, 1.0, 0.0))
}

/// Distance from `q` to the line through `p` with unit direction `dir`.
pub fn dist_point_line(q: V3, p: V3, dir: V3) -> f64 {
    q.sub(p).reject(dir).norm()
}

/// Cyclic Jacobi eigen-decomposition of a symmetric 3x3 matrix.
///
/// Returns `(eigenvalues, eigenvectors)` sorted by ascending eigenvalue;
/// entry `i` of the vectors is the eigenvector for `values[i]`.
pub fn jacobi3(input: [[f64; 3]; 3]) -> ([f64; 3], [V3; 3]) {
    let mut a = input;
    let mut v = [[0.0_f64; 3]; 3];
    for (i, row) in v.iter_mut().enumerate() {
        row[i] = 1.0;
    }
    for _ in 0..64 {
        let off = a[0][1].abs() + a[0][2].abs() + a[1][2].abs();
        if off < 1e-18 {
            break;
        }
        for (p, q) in [(0_usize, 1_usize), (0, 2), (1, 2)] {
            let apq = a[p][q];
            if apq.abs() < 1e-300 {
                continue;
            }
            let theta = (a[q][q] - a[p][p]) / (2.0 * apq);
            let t = if theta >= 0.0 {
                1.0 / (theta + theta.mul_add(theta, 1.0).sqrt())
            } else {
                -1.0 / (-theta + theta.mul_add(theta, 1.0).sqrt())
            };
            let c = 1.0 / t.mul_add(t, 1.0).sqrt();
            let s = t * c;
            for k in 0..3 {
                let akp = a[k][p];
                let akq = a[k][q];
                a[k][p] = c * akp - s * akq;
                a[k][q] = s.mul_add(akp, c * akq);
            }
            for k in 0..3 {
                let apk = a[p][k];
                let aqk = a[q][k];
                a[p][k] = c * apk - s * aqk;
                a[q][k] = s.mul_add(apk, c * aqk);
            }
            for row in &mut v {
                let vp = row[p];
                let vq = row[q];
                row[p] = c * vp - s * vq;
                row[q] = s.mul_add(vp, c * vq);
            }
        }
    }
    let mut order = [0_usize, 1, 2];
    order.sort_by(|&i, &j| a[i][i].total_cmp(&a[j][j]));
    let values = [
        a[order[0]][order[0]],
        a[order[1]][order[1]],
        a[order[2]][order[2]],
    ];
    let vecs = [
        V3::new(v[0][order[0]], v[1][order[0]], v[2][order[0]]),
        V3::new(v[0][order[1]], v[1][order[1]], v[2][order[1]]),
        V3::new(v[0][order[2]], v[1][order[2]], v[2][order[2]]),
    ];
    (values, vecs)
}

/// Gaussian elimination with partial pivoting for `n <= 4`.
///
/// `None` when the system is singular to working precision.
pub fn solve_small(n: usize, m: &[[f64; 4]; 4], rhs: &[f64; 4]) -> Option<[f64; 4]> {
    let mut a = *m;
    let mut b = *rhs;
    for col in 0..n {
        let mut piv = col;
        for r in col + 1..n {
            if a[r][col].abs() > a[piv][col].abs() {
                piv = r;
            }
        }
        if a[piv][col].abs() < 1e-14 {
            return None;
        }
        a.swap(col, piv);
        b.swap(col, piv);
        for r in col + 1..n {
            let f = a[r][col] / a[col][col];
            for c in col..n {
                a[r][c] -= f * a[col][c];
            }
            b[r] -= f * b[col];
        }
    }
    let mut x = [0.0_f64; 4];
    for i in (0..n).rev() {
        let mut acc = b[i];
        for j in i + 1..n {
            acc -= a[i][j] * x[j];
        }
        x[i] = acc / a[i][i];
    }
    Some(x)
}

/// Weighted least squares for a straight line `y = m x + c`.
///
/// `None` when the samples carry no spread in `x`.
pub fn fit_line(samples: &[(f64, f64, f64)]) -> Option<(f64, f64)> {
    let mut sw = 0.0;
    let mut sx = 0.0;
    let mut sy = 0.0;
    let mut sxx = 0.0;
    let mut sxy = 0.0;
    for &(x, y, w) in samples {
        sw += w;
        sx += w * x;
        sy += w * y;
        sxx += w * x * x;
        sxy += w * x * y;
    }
    if sw <= 0.0 {
        return None;
    }
    let det = sxx.mul_add(sw, -(sx * sx));
    if det.abs() < 1e-300 {
        return None;
    }
    let m = sxy.mul_add(sw, -(sx * sy)) / det;
    let c = sxx.mul_add(sy, -(sx * sxy)) / det;
    Some((m, c))
}
