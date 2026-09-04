//! The four segmentation stages: smooth over-segmentation, primitive fitting,
//! primitive-agreement merging, and boundary refinement.

use std::collections::{BTreeMap, HashMap, HashSet};

use super::fit::{FaceRef, Fit, FitOpts, Sample, fit_patch};
use super::linalg::{V3, angle_between, angle_undirected, dist_point_line};
use super::{PatchKind, Primitive};
use crate::mesh::WeldedMesh;

/// One triangle's geometry, computed once and reused by every stage.
pub(super) struct FaceGeom {
    /// Welded corner indices.
    pub v: [u32; 3],
    /// Unit normal.
    pub normal: V3,
    /// Area.
    pub area: f64,
    /// Centroid.
    pub centroid: V3,
}

/// The welded mesh plus the per-triangle geometry the fits need.
pub(super) struct Geom<'a> {
    /// Welded vertex positions.
    pub verts: Vec<V3>,
    /// Per-triangle geometry, indexed as the welded mesh's triangles are.
    pub faces: Vec<FaceGeom>,
    /// Per-triangle neighbours, borrowed from the welded mesh.
    pub neighbours: &'a [Vec<u32>],
}

impl<'a> Geom<'a> {
    pub(super) fn new(welded: &'a WeldedMesh) -> Self {
        let verts: Vec<V3> = welded.positions.iter().map(|p| V3::from_arr(*p)).collect();
        let faces = welded
            .triangles
            .iter()
            .map(|t| {
                let (a, b, c) = (
                    verts.get(t[0] as usize).copied().unwrap_or(V3::ZERO),
                    verts.get(t[1] as usize).copied().unwrap_or(V3::ZERO),
                    verts.get(t[2] as usize).copied().unwrap_or(V3::ZERO),
                );
                let cross = b.sub(a).cross(c.sub(a));
                FaceGeom {
                    v: *t,
                    normal: cross.unit().unwrap_or(V3::new(0.0, 0.0, 1.0)),
                    area: 0.5 * cross.norm(),
                    centroid: a.add(b).add(c).mul(1.0 / 3.0),
                }
            })
            .collect();
        Self {
            verts,
            faces,
            neighbours: &welded.neighbours,
        }
    }

    /// Total surface area of the welded mesh.
    pub(super) fn total_area(&self) -> f64 {
        self.faces.iter().map(|f| f.area).sum()
    }

    /// Median triangle edge length over the whole mesh.
    ///
    /// This is only the fallback: every stage below prefers the patch's own
    /// median. Every interior edge is counted twice, once from each side, which
    /// cannot move a median of a set that is dominated by interior edges.
    pub(super) fn median_edge_length(&self) -> f64 {
        let mut lengths: Vec<f64> = Vec::with_capacity(self.faces.len() * 3);
        for f in &self.faces {
            self.push_edges(f, &mut lengths);
        }
        median(&mut lengths)
    }

    /// Median triangle edge length over the triangles named by `faces`.
    fn median_edge_of(&self, faces: &[u32]) -> f64 {
        let mut lengths: Vec<f64> = Vec::with_capacity(faces.len() * 3);
        for &f in faces {
            let Some(face) = self.faces.get(f as usize) else {
                continue;
            };
            self.push_edges(face, &mut lengths);
        }
        median(&mut lengths)
    }

    fn push_edges(&self, face: &FaceGeom, out: &mut Vec<f64>) {
        for k in 0..3 {
            let (Some(&a), Some(&b)) = (
                self.verts.get(face.v[k] as usize),
                self.verts.get(face.v[(k + 1) % 3] as usize),
            ) else {
                continue;
            };
            out.push(a.sub(b).norm());
        }
    }

    fn area_of(&self, faces: &[u32]) -> f64 {
        faces
            .iter()
            .filter_map(|&f| self.faces.get(f as usize))
            .map(|f| f.area)
            .sum()
    }

    fn neighbours_of(&self, f: u32) -> &[u32] {
        self.neighbours
            .get(f as usize)
            .map_or(&[][..], Vec::as_slice)
    }
}

fn median(lengths: &mut [f64]) -> f64 {
    if lengths.is_empty() {
        return 0.0;
    }
    let mid = lengths.len() / 2;
    lengths.sort_by(f64::total_cmp);
    lengths.get(mid).copied().unwrap_or(0.0)
}

/// A patch with fewer triangles than this has too few edges for its own median
/// to be evidence of anything, so it borrows the mesh-level tolerance. One
/// triangle in particular has its median decided by a single edge, and a sliver
/// seed would drive the tolerance to nothing.
const MIN_TOL_FACES: usize = 2;

/// The residual budget for one patch: `tol_chord_factor` times **its own**
/// median edge length, clamped.
///
/// Per patch, not per mesh: a part with both a coarsely tessellated 900 mm
/// plate and finely tessellated 5 mm fillets has no single right answer. A
/// mesh-wide median is 3.7 mm on the NIST test part, enough to merge two
/// tangent 50 mm bosses into one surface, and the bosses are exactly the
/// patches whose own chords are short enough to say so.
fn patch_tol(g: &Geom, faces: &[u32], p: &Params) -> f64 {
    if faces.len() < MIN_TOL_FACES {
        return p.opts.tol;
    }
    let m = g.median_edge_of(faces);
    if !(m.is_finite() && m > 0.0) {
        return p.opts.tol;
    }
    // Never looser than the mesh-wide value. A patch's chords are long either
    // because the surface is finely modelled and gently curved, or because it
    // is flat and the tessellator spent two triangles on it; the second case is
    // the common one, and a flat face needs no slack at all. Letting a coarse
    // flat claim a proportionally huge budget lets boundary refinement pull
    // half the part into it — on the NIST plate that is one Unknown blob over
    // 53% of the area. Downward is where the useful signal is: a finely
    // tessellated boss gets the tight budget that keeps it off its neighbour.
    let m = m.min(p.mesh_edge);
    (p.tol_chord_factor * m).clamp(p.tol_lo, p.tol_hi)
}

/// Resolved parameters for one run. All angles in radians, all lengths
/// absolute and already derived from the mesh.
pub(super) struct Params {
    /// Dihedral threshold for the initial over-segmentation.
    pub angle_rad: f64,
    /// Fitting tolerances and guards. `opts.tol` is only the **mesh-level
    /// fallback**: every stage overrides it with the patch's own tolerance from
    /// [`patch_tol`].
    pub opts: FitOpts,
    /// Tolerance as a multiple of a patch's own median edge length.
    pub tol_chord_factor: f64,
    /// Absolute lower clamp on a patch's tolerance.
    pub tol_lo: f64,
    /// Absolute upper clamp on a patch's tolerance.
    pub tol_hi: f64,
    /// The mesh-wide median edge length.
    pub mesh_edge: f64,
    /// Direction slack when two fitted primitives are declared the same.
    pub merge_angle_rad: f64,
    /// Half-angle slack when two fitted cones are declared the same.
    pub merge_half_angle_rad: f64,
    /// Radius slack, as a fraction, for cylinders and spheres.
    pub merge_radius_frac: f64,
    /// Radius slack, as a fraction, for tori.
    pub merge_torus_radius_frac: f64,
    /// Cap on merge rounds.
    pub max_merge_rounds: usize,
    /// Boundary refinement rounds.
    pub refine_rounds: usize,
    /// How many times a patch that fitted nothing may be re-cut.
    pub split_levels: usize,
    /// Fit face centroids instead of patch vertices.
    pub fit_on_centroids: bool,
}

/// The raw result of the stages, before promotion policy is applied.
pub(super) struct Grown {
    /// Face indices per patch, largest patch first.
    pub patches: Vec<Vec<u32>>,
    /// The fit of each patch.
    pub fits: Vec<Fit>,
    /// Whether the patch was carved out of a region that fitted nothing.
    pub carved: Vec<bool>,
}

struct Uf {
    parent: Vec<usize>,
}

impl Uf {
    fn new(n: usize) -> Self {
        Self {
            parent: (0..n).collect(),
        }
    }

    fn find(&mut self, mut x: usize) -> usize {
        while self.parent.get(x).copied().unwrap_or(x) != x {
            let p = self.parent.get(x).copied().unwrap_or(x);
            let g = self.parent.get(p).copied().unwrap_or(p);
            if let Some(slot) = self.parent.get_mut(x) {
                *slot = g;
            }
            x = g;
        }
        x
    }

    fn union(&mut self, a: usize, b: usize) -> bool {
        let (ra, rb) = (self.find(a), self.find(b));
        if ra == rb {
            return false;
        }
        if let Some(slot) = self.parent.get_mut(rb) {
            *slot = ra;
        }
        true
    }
}

/// Weighted sample points and area-weighted normals for one patch.
fn gather(g: &Geom, faces: &[u32], centroids: bool) -> (Vec<Sample>, Vec<FaceRef>) {
    let refs: Vec<FaceRef> = faces
        .iter()
        .filter_map(|&f| {
            g.faces.get(f as usize).map(|x| FaceRef {
                n: x.normal,
                c: x.centroid,
                a: x.area,
            })
        })
        .collect();
    if centroids {
        let pts = faces
            .iter()
            .filter_map(|&f| {
                g.faces.get(f as usize).map(|x| Sample {
                    p: x.centroid,
                    w: x.area,
                })
            })
            .collect();
        return (pts, refs);
    }
    // Vertices, not centroids, and in vertex order: the sample order decides
    // the floating-point summation order inside every fit, so it has to be
    // reproducible from run to run.
    let mut w: BTreeMap<u32, f64> = BTreeMap::new();
    for &f in faces {
        let Some(face) = g.faces.get(f as usize) else {
            continue;
        };
        for v in face.v {
            *w.entry(v).or_insert(0.0) += face.area / 3.0;
        }
    }
    let pts = w
        .into_iter()
        .filter_map(|(v, weight)| g.verts.get(v as usize).map(|&p| Sample { p, w: weight }))
        .collect();
    (pts, refs)
}

/// The sharpest crease inside a face set: the largest angle between the normals
/// of two triangles of the set that share an edge.
///
/// This is the one thing only the caller of a fit can measure, and it is what
/// separates a coarsely tessellated curve from a polyhedron.
///
/// Measured undirected, as [`same_surface`] and the fits' own normal deviation
/// are: a triangle wound the other way round from its neighbour is a bookkeeping
/// artefact of the tessellation, not a fold in the surface, and a planar
/// rectangle-to-circle triangulation is full of them. Degenerate triangles are
/// skipped outright, because [`Geom::new`] gives them an arbitrary normal and
/// one sliver must not be able to veto a real cylinder.
fn max_crease(g: &Geom, faces: &[u32]) -> f64 {
    let own: HashSet<u32> = faces.iter().copied().collect();
    let mut worst: f64 = 0.0;
    for &f in faces {
        let Some(fg) = g.faces.get(f as usize) else {
            continue;
        };
        if fg.area <= 0.0 {
            continue;
        }
        for &h in g.neighbours_of(f) {
            if h <= f || !own.contains(&h) {
                continue;
            }
            let Some(hg) = g.faces.get(h as usize) else {
                continue;
            };
            if hg.area <= 0.0 {
                continue;
            }
            worst = worst.max(angle_undirected(fg.normal, hg.normal));
        }
    }
    worst
}

/// Fit a face set against a tolerance chosen by the caller: a freshly cut patch
/// is judged against its own chords ([`patch_tol`]), while a trial merge is
/// judged against the looser of the two patches it joins.
fn fit_faces_at(g: &Geom, faces: &[u32], p: &Params, tol: f64) -> Fit {
    let (pts, refs) = gather(g, faces, p.fit_on_centroids);
    let crease = max_crease(g, faces);
    fit_patch(
        &pts,
        &refs,
        FitOpts {
            tol,
            max_crease: crease,
            ..p.opts
        },
    )
}

/// Do two independently fitted primitives describe the same surface?
fn same_surface(a: Primitive, b: Primitive, tol: f64, p: &Params) -> bool {
    let close = |x: f64, y: f64, frac: f64| (x - y).abs() <= frac * x.abs().max(y.abs());
    match (a, b) {
        (
            Primitive::Plane {
                normal: n1,
                offset: d1,
            },
            Primitive::Plane {
                normal: n2,
                offset: d2,
            },
        ) => {
            let (n1, n2) = (V3::from_arr(n1), V3::from_arr(n2));
            let flip = if n1.dot(n2) >= 0.0 { 1.0 } else { -1.0 };
            angle_undirected(n1, n2) < p.merge_angle_rad && (d1 - flip * d2).abs() < tol
        }
        (
            Primitive::Cylinder {
                axis_point: p1,
                axis_dir: d1,
                radius: r1,
                ..
            },
            Primitive::Cylinder {
                axis_point: p2,
                axis_dir: d2,
                radius: r2,
                ..
            },
        ) => {
            let (d1, d2) = (V3::from_arr(d1), V3::from_arr(d2));
            angle_undirected(d1, d2) < p.merge_angle_rad
                && close(r1, r2, p.merge_radius_frac)
                && dist_point_line(V3::from_arr(p2), V3::from_arr(p1), d1) < tol
        }
        (
            Primitive::Cone {
                apex: a1,
                axis_dir: d1,
                half_angle_deg: h1,
            },
            Primitive::Cone {
                apex: a2,
                axis_dir: d2,
                half_angle_deg: h2,
            },
        ) => {
            angle_undirected(V3::from_arr(d1), V3::from_arr(d2)) < p.merge_angle_rad
                && V3::from_arr(a1).sub(V3::from_arr(a2)).norm() < tol
                && (h1 - h2).abs().to_radians() < p.merge_half_angle_rad
        }
        (
            Primitive::Torus {
                center: c1,
                axis_dir: d1,
                major_radius: r1,
                minor_radius: m1,
            },
            Primitive::Torus {
                center: c2,
                axis_dir: d2,
                major_radius: r2,
                minor_radius: m2,
            },
        ) => {
            angle_undirected(V3::from_arr(d1), V3::from_arr(d2)) < p.merge_angle_rad
                && V3::from_arr(c1).sub(V3::from_arr(c2)).norm() < tol
                && close(r1, r2, p.merge_torus_radius_frac)
                && close(m1, m2, p.merge_torus_radius_frac)
        }
        (
            Primitive::Sphere {
                center: c1,
                radius: r1,
            },
            Primitive::Sphere {
                center: c2,
                radius: r2,
            },
        ) => {
            V3::from_arr(c1).sub(V3::from_arr(c2)).norm() < tol
                && close(r1, r2, p.merge_radius_frac)
        }
        _ => false,
    }
}

/// Only patches that already agree on a primitive type (or one that fitted
/// nothing) may be trial-merged. A small plane tangent to a large cylinder does
/// sit inside that cylinder's residual budget, so allowing cross-type merges
/// silently eats real planar faces.
fn mergeable_types(a: Primitive, b: Primitive) -> bool {
    PatchKind::of(a) == PatchKind::Unknown
        || PatchKind::of(b) == PatchKind::Unknown
        || PatchKind::of(a) == PatchKind::of(b)
}

/// A merge is only taken when the union fits as a primitive *everywhere*. The
/// area-weighted RMS alone lets a large well-fitting patch hide a small one
/// that has been dragged onto the wrong surface, which is how a chain of greedy
/// merges invents a shallow large-radius cylinder out of two planes.
fn accept_merge(f: Fit, tol: f64) -> bool {
    PatchKind::of(f.prim) != PatchKind::Unknown && f.rms <= tol && f.max_res <= 2.0 * tol
}

/// Adjacent patch pairs, each listed once, in a deterministic order.
fn patch_pairs(g: &Geom, label: &[usize]) -> Vec<(usize, usize)> {
    let mut seen: HashSet<(usize, usize)> = HashSet::new();
    for i in 0..g.faces.len() {
        let Some(&li) = label.get(i) else { continue };
        for &j in g.neighbours_of(i as u32) {
            let Some(&lj) = label.get(j as usize) else {
                continue;
            };
            if li != lj {
                seen.insert(if li < lj { (li, lj) } else { (lj, li) });
            }
        }
    }
    let mut out: Vec<(usize, usize)> = seen.into_iter().collect();
    out.sort_unstable();
    out
}

/// Collapse merged patches, re-index the labels, and carry provenance: a union
/// is only "carved" when every part of it was, and it inherits the *loosest*
/// tolerance of its parts.
///
/// The tolerance has to be the max rather than the union's own median edge,
/// because that is the budget the merge was accepted under. Re-deriving it from
/// the union would let a merge accepted at one tolerance be re-fitted at a
/// tighter one, which silently turns a just-merged patch into a huge `Unknown`
/// blob that nothing ever un-merges.
fn rebuild(state: &mut State, label: &mut [usize], uf: &mut Uf) {
    let mut remap: HashMap<usize, usize> = HashMap::new();
    let mut new_patches: Vec<Vec<u32>> = Vec::new();
    let mut new_fits: Vec<Fit> = Vec::new();
    let mut new_carved: Vec<bool> = Vec::new();
    let mut new_tols: Vec<f64> = Vec::new();
    for old in 0..state.patches.len() {
        let root = uf.find(old);
        let was_carved = state.carved.get(old).copied().unwrap_or(false);
        let tol = state.tols.get(old).copied().unwrap_or(0.0);
        if let Some(&idx) = remap.get(&root) {
            let taken = std::mem::take(&mut state.patches[old]);
            new_patches[idx].extend(taken);
            new_carved[idx] = new_carved[idx] && was_carved;
            new_tols[idx] = new_tols[idx].max(tol);
        } else {
            let idx = new_patches.len();
            remap.insert(root, idx);
            new_patches.push(std::mem::take(&mut state.patches[old]));
            new_fits.push(state.fits.get(root).copied().unwrap_or(Fit::UNKNOWN));
            new_carved.push(was_carved);
            new_tols.push(tol);
        }
    }
    for (idx, faces) in new_patches.iter().enumerate() {
        for &f in faces {
            if let Some(slot) = label.get_mut(f as usize) {
                *slot = idx;
            }
        }
    }
    state.patches = new_patches;
    state.fits = new_fits;
    state.carved = new_carved;
    state.tols = new_tols;
}

/// Face-level score against a candidate primitive: surface distance at the
/// triangle's vertices plus its normal deviation scaled to a length.
fn face_score(g: &Geom, fi: usize, prim: Primitive) -> f64 {
    let Some(face) = g.faces.get(fi) else {
        return f64::INFINITY;
    };
    if PatchKind::of(prim) == PatchKind::Unknown {
        return f64::INFINITY;
    }
    let mut dist = 0.0;
    for v in face.v {
        let Some(&p) = g.verts.get(v as usize) else {
            return f64::INFINITY;
        };
        dist += prim.residual(p);
    }
    dist /= 3.0;
    let ang = prim
        .normal_at(face.centroid)
        .map_or(core::f64::consts::FRAC_PI_2, |n| {
            let a = angle_between(face.normal, n);
            a.min(core::f64::consts::PI - a)
        });
    ang.mul_add(face.area.sqrt(), dist)
}

/// Would moving face `f` into patch `to` put a crease inside that patch?
///
/// Boundary refinement scores a face against a neighbouring patch's fitted
/// primitive, and [`face_score`] says nothing about the angle the face meets
/// that patch at: a chamfer facet lying close to a big flat's plane is scored
/// well by it and moves there, folded — and a face whose own patch fitted
/// nothing scores infinity at home, so it moves wherever it is touched. That is
/// how a clean surface acquires a fold it can never lose: nothing after this
/// stage re-cuts a patch, and the crease rule in [`fit_patch`] then refuses the
/// whole face rather than the one triangle that spoiled it. A face may only
/// join a patch it does not fold, measured exactly as that rule measures it.
fn joins_smoothly(g: &Geom, f: u32, to: usize, label: &[usize], max_step: f64) -> bool {
    let Some(fg) = g.faces.get(f as usize) else {
        return false;
    };
    // A degenerate triangle's normal is arbitrary, so it can neither fold a
    // patch nor be kept out of one by a fold that is not there.
    if fg.area <= 0.0 {
        return true;
    }
    g.neighbours_of(f).iter().all(|&h| {
        if label.get(h as usize).copied() != Some(to) {
            return true;
        }
        g.faces
            .get(h as usize)
            .is_none_or(|hg| hg.area <= 0.0 || angle_undirected(fg.normal, hg.normal) <= max_step)
    })
}

/// Re-cut one patch at a tighter dihedral angle, using only its own faces.
fn split_patch(g: &Geom, faces: &[u32], label: &[usize], angle: f64) -> Vec<Vec<u32>> {
    let own = faces
        .first()
        .and_then(|&f| label.get(f as usize).copied())
        .unwrap_or(usize::MAX);
    let local: HashMap<u32, usize> = faces.iter().enumerate().map(|(i, &f)| (f, i)).collect();
    let mut uf = Uf::new(faces.len());
    for (i, &f) in faces.iter().enumerate() {
        let Some(fg) = g.faces.get(f as usize) else {
            continue;
        };
        for &h in g.neighbours_of(f) {
            if label.get(h as usize).copied() != Some(own) {
                continue;
            }
            let (Some(&j), Some(hg)) = (local.get(&h), g.faces.get(h as usize)) else {
                continue;
            };
            if j > i && angle_between(fg.normal, hg.normal) < angle {
                uf.union(i, j);
            }
        }
    }
    let mut groups: HashMap<usize, Vec<u32>> = HashMap::new();
    let mut order: Vec<usize> = Vec::new();
    for (i, &f) in faces.iter().enumerate() {
        let r = uf.find(i);
        if !groups.contains_key(&r) {
            order.push(r);
        }
        groups.entry(r).or_default().push(f);
    }
    order
        .into_iter()
        .filter_map(|r| groups.remove(&r))
        .collect()
}

/// The mutable state the stages pass around: one entry per patch, in step.
struct State {
    patches: Vec<Vec<u32>>,
    fits: Vec<Fit>,
    carved: Vec<bool>,
    /// The residual budget each patch is judged against. Derived from the
    /// patch's own edge lengths when it is first cut, and the max of its parts
    /// once it has been merged.
    tols: Vec<f64>,
}

impl State {
    /// Derive every patch's tolerance from its own triangles and refit. Used
    /// where the patches have just been cut, so no merge budget exists to
    /// inherit.
    fn refit_fresh(&mut self, g: &Geom, p: &Params) {
        self.tols = self.patches.iter().map(|f| patch_tol(g, f, p)).collect();
        self.refit(g, p);
    }

    /// Refit every patch against the tolerance it already carries.
    fn refit(&mut self, g: &Geom, p: &Params) {
        for (i, faces) in self.patches.iter().enumerate() {
            self.fits[i] = fit_faces_at(g, faces, p, self.tols[i]);
        }
    }
}

pub(super) fn run(g: &Geom, p: &Params) -> Grown {
    let nf = g.faces.len();

    // ── stage 1: smooth over-segmentation ─────────────────────────
    let mut uf = Uf::new(nf);
    for i in 0..nf {
        for &j in g.neighbours_of(i as u32) {
            let j = j as usize;
            let (Some(fi), Some(fj)) = (g.faces.get(i), g.faces.get(j)) else {
                continue;
            };
            if j > i && angle_between(fi.normal, fj.normal) < p.angle_rad {
                uf.union(i, j);
            }
        }
    }
    let mut label = vec![0_usize; nf];
    let mut patches: Vec<Vec<u32>> = Vec::new();
    let mut index: HashMap<usize, usize> = HashMap::new();
    for f in 0..nf {
        let root = uf.find(f);
        let idx = *index.entry(root).or_insert_with(|| {
            patches.push(Vec::new());
            patches.len() - 1
        });
        label[f] = idx;
        patches[idx].push(f as u32);
    }

    // ── stage 2: fit every patch ──────────────────────────────────
    let n = patches.len();
    let mut st = State {
        patches,
        fits: vec![Fit::UNKNOWN; n],
        carved: vec![false; n],
        tols: vec![p.opts.tol; n],
    };
    st.refit_fresh(g, p);

    // ── stage 2b: split patches that fitted nothing ───────────────
    //
    // A vertical fillet is tangent to the planes it joins, so a pure dihedral
    // threshold leaks plane -> fillet -> plane into one blob that fits no
    // primitive. Re-cut such a blob at a progressively tighter angle; stage 3
    // then re-joins the pieces that really do share a surface. Everything cut
    // out this way is marked `carved`, because splitting far enough eventually
    // makes any triangle pair look planar and those shards must not be
    // promoted to real surfaces on their own.
    let mut split_angle = p.angle_rad;
    for _ in 0..p.split_levels {
        if st
            .fits
            .iter()
            .all(|f| PatchKind::of(f.prim) != PatchKind::Unknown)
        {
            break;
        }
        // Keep tightening even when a level changes nothing: the leak may only
        // break at a threshold two levels down.
        split_angle = (split_angle / 3.0).max(0.5_f64.to_radians());
        let mut next: Vec<Vec<u32>> = Vec::new();
        let mut next_carved: Vec<bool> = Vec::new();
        let mut changed = false;
        for (i, faces) in st.patches.iter().enumerate() {
            let was_carved = st.carved.get(i).copied().unwrap_or(false);
            if PatchKind::of(st.fits[i].prim) != PatchKind::Unknown || faces.len() < 2 {
                next.push(faces.clone());
                next_carved.push(was_carved);
                continue;
            }
            let parts = split_patch(g, faces, &label, split_angle);
            let split = parts.len() > 1;
            changed |= split;
            for part in parts {
                next.push(part);
                next_carved.push(was_carved || split);
            }
        }
        if !changed {
            continue;
        }
        st.patches = next;
        st.carved = next_carved;
        st.fits = vec![Fit::UNKNOWN; st.patches.len()];
        for (idx, faces) in st.patches.iter().enumerate() {
            for &f in faces {
                label[f as usize] = idx;
            }
        }
        // Fresh cuts, so each shard is judged against its own chords.
        st.refit_fresh(g, p);
    }

    // ── stage 3: merge patches whose primitives agree ─────────────
    for _ in 0..p.max_merge_rounds {
        let pairs = patch_pairs(g, &label);
        // Rank: agreeing primitives first, then trial merges by fit quality.
        let mut cands: Vec<(f64, usize, usize)> = Vec::new();
        for &(a, b) in &pairs {
            // A merge is judged by the looser of the two patches: the finer
            // one's tolerance would reject the coarser one's own chords.
            let tol = st.tols[a].max(st.tols[b]);
            if same_surface(st.fits[a].prim, st.fits[b].prim, tol, p) {
                cands.push((-1.0, a, b));
                continue;
            }
            if !mergeable_types(st.fits[a].prim, st.fits[b].prim) {
                continue;
            }
            let mut faces = st.patches[a].clone();
            faces.extend_from_slice(&st.patches[b]);
            let f = fit_faces_at(g, &faces, p, tol);
            if accept_merge(f, tol) {
                cands.push((f.rms, a, b));
            }
        }
        if cands.is_empty() {
            break;
        }
        cands.sort_by(|x, y| x.0.total_cmp(&y.0));

        let mut round_uf = Uf::new(st.patches.len());
        let mut merged: HashMap<usize, (Vec<u32>, f64)> = HashMap::new();
        let mut changed = false;
        for (_, a, b) in cands {
            let (ra, rb) = (round_uf.find(a), round_uf.find(b));
            if ra == rb {
                continue;
            }
            let (fa, ta) = merged
                .get(&ra)
                .map_or((&st.patches[ra], st.tols[ra]), |(f, t)| (f, *t));
            let (fb, tb) = merged
                .get(&rb)
                .map_or((&st.patches[rb], st.tols[rb]), |(f, t)| (f, *t));
            let tol = ta.max(tb);
            let mut faces = fa.clone();
            faces.extend_from_slice(fb);
            // Re-fit the actual union before committing, so a chain of merges
            // cannot drift away from a surface any single step accepted.
            if !accept_merge(fit_faces_at(g, &faces, p, tol), tol) {
                continue;
            }
            round_uf.union(ra, rb);
            let root = round_uf.find(ra);
            merged.remove(&ra);
            merged.remove(&rb);
            merged.insert(root, (faces, tol));
            changed = true;
        }
        if !changed {
            break;
        }
        rebuild(&mut st, &mut label, &mut round_uf);
        st.refit(g, p);
    }

    // ── stage 4: boundary refinement + unknown absorption ─────────
    for _ in 0..p.refine_rounds {
        let mut moves: Vec<(usize, usize)> = Vec::new();
        for i in 0..nf {
            let own = label[i];
            let own_score = face_score(g, i, st.fits[own].prim);
            let mut best = (own_score, own);
            for &j in g.neighbours_of(i as u32) {
                let lj = label[j as usize];
                if lj == own {
                    continue;
                }
                let s = face_score(g, i, st.fits[lj].prim);
                if s < best.0 * 0.999
                    && s <= st.tols[lj]
                    && joins_smoothly(g, i as u32, lj, &label, p.opts.max_facet_step)
                {
                    best = (s, lj);
                }
            }
            if best.1 != own {
                moves.push((i, best.1));
            }
        }
        if moves.is_empty() {
            break;
        }
        for (f, to) in moves {
            let from = label[f];
            if st.patches[from].len() <= 1 {
                continue;
            }
            st.patches[from].retain(|&x| x != f as u32);
            st.patches[to].push(f as u32);
            label[f] = to;
        }
        st.refit(g, p);
    }

    // Unknown patches that complete an adjacent primitive get absorbed by it.
    for _ in 0..2 {
        let pairs = patch_pairs(g, &label);
        let mut cands: Vec<(f64, usize, usize)> = Vec::new();
        for &(a, b) in &pairs {
            let a_unknown = PatchKind::of(st.fits[a].prim) == PatchKind::Unknown;
            let b_unknown = PatchKind::of(st.fits[b].prim) == PatchKind::Unknown;
            if a_unknown == b_unknown {
                continue;
            }
            let tol = st.tols[a].max(st.tols[b]);
            let mut faces = st.patches[a].clone();
            faces.extend_from_slice(&st.patches[b]);
            let f = fit_faces_at(g, &faces, p, tol);
            if accept_merge(f, tol) {
                cands.push((f.rms, a, b));
            }
        }
        if cands.is_empty() {
            break;
        }
        cands.sort_by(|x, y| x.0.total_cmp(&y.0));
        let mut round_uf = Uf::new(st.patches.len());
        let mut changed = false;
        for (_, a, b) in cands {
            changed |= round_uf.union(a, b);
        }
        if !changed {
            break;
        }
        rebuild(&mut st, &mut label, &mut round_uf);
        st.refit(g, p);
    }

    let State {
        patches,
        fits,
        carved,
        ..
    } = st;
    // Stable ids: largest patch first.
    let mut order: Vec<usize> = (0..patches.len()).collect();
    order.sort_by(|&a, &b| g.area_of(&patches[b]).total_cmp(&g.area_of(&patches[a])));
    Grown {
        patches: order.iter().map(|&i| patches[i].clone()).collect(),
        fits: order.iter().map(|&i| fits[i]).collect(),
        carved: order
            .iter()
            .map(|&i| carved.get(i).copied().unwrap_or(false))
            .collect(),
    }
}
