//! The four segmentation stages: smooth over-segmentation, primitive fitting,
//! primitive-agreement merging, and boundary refinement.

use std::collections::HashMap;

use crate::fit::{FaceRef, Fit, FitOpts, Prim, Sample, fit_patch};
use crate::linalg::{V3, angle_between, angle_undirected};
use crate::mesh::Mesh;

pub struct Params {
    pub angle_rad: f64,
    pub opts: FitOpts,
    /// Direction/offset slack when two fitted primitives are declared the same.
    pub merge_angle_rad: f64,
    pub merge_radius_frac: f64,
    pub max_merge_rounds: usize,
    pub refine_rounds: usize,
    /// How many times an unfitted patch may be re-cut at a tighter angle.
    pub split_levels: usize,
    pub fit_on_centroids: bool,
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
        while self.parent[x] != x {
            let g = self.parent[self.parent[x]];
            self.parent[x] = g;
            x = g;
        }
        x
    }
    fn union(&mut self, a: usize, b: usize) -> bool {
        let (ra, rb) = (self.find(a), self.find(b));
        if ra == rb {
            return false;
        }
        self.parent[rb] = ra;
        true
    }
}

pub struct Segmentation {
    pub patches: Vec<Vec<usize>>,
    pub fits: Vec<Fit>,
}

pub struct Timings {
    pub stage1_ms: f64,
    pub stage2_ms: f64,
    pub stage3_ms: f64,
    pub stage4_ms: f64,
    pub merge_rounds: usize,
}

fn now() -> std::time::Instant {
    std::time::Instant::now()
}
fn ms(t: std::time::Instant) -> f64 {
    t.elapsed().as_secs_f64() * 1000.0
}

/// Weighted sample points and area-weighted normals for one patch.
fn gather(mesh: &Mesh, faces: &[usize], centroids: bool) -> (Vec<Sample>, Vec<FaceRef>) {
    let refs: Vec<FaceRef> = faces
        .iter()
        .filter_map(|&f| {
            mesh.faces.get(f).map(|x| FaceRef {
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
                mesh.faces.get(f).map(|x| Sample {
                    p: x.centroid,
                    w: x.area,
                })
            })
            .collect();
        return (pts, refs);
    }
    // Vertices, not centroids: a tessellation samples the analytic surface at
    // its vertices, so a coarse cylinder's radius is only recoverable there.
    let mut w: HashMap<u32, f64> = HashMap::new();
    for &f in faces {
        let Some(face) = mesh.faces.get(f) else { continue };
        for v in face.v {
            *w.entry(v).or_insert(0.0) += face.area / 3.0;
        }
    }
    let pts = w
        .into_iter()
        .filter_map(|(v, weight)| {
            mesh.verts.get(v as usize).map(|&p| Sample { p, w: weight })
        })
        .collect();
    (pts, refs)
}

fn fit_faces(mesh: &Mesh, faces: &[usize], p: &Params) -> Fit {
    let (pts, refs) = gather(mesh, faces, p.fit_on_centroids);
    fit_patch(&pts, &refs, p.opts)
}

fn dist_point_line(q: V3, p: V3, dir: V3) -> f64 {
    let rel = q.sub(p);
    rel.sub(dir.mul(rel.dot(dir))).norm()
}

/// Do two independently fitted primitives describe the same surface?
fn same_surface(a: Prim, b: Prim, p: &Params) -> bool {
    let tol = p.opts.tol;
    match (a, b) {
        (Prim::Plane { n: n1, d: d1 }, Prim::Plane { n: n2, d: d2 }) => {
            let flip = if n1.dot(n2) >= 0.0 { 1.0 } else { -1.0 };
            angle_undirected(n1, n2) < p.merge_angle_rad && (d1 - flip * d2).abs() < tol
        }
        (
            Prim::Cylinder { p: p1, dir: d1, r: r1, .. },
            Prim::Cylinder { p: p2, dir: d2, r: r2, .. },
        ) => {
            angle_undirected(d1, d2) < p.merge_angle_rad
                && (r1 - r2).abs() <= p.merge_radius_frac * r1.max(r2)
                && dist_point_line(p2, p1, d1) < tol
        }
        (Prim::Sphere { c: c1, r: r1 }, Prim::Sphere { c: c2, r: r2 }) => {
            c1.sub(c2).norm() < tol && (r1 - r2).abs() <= p.merge_radius_frac * r1.max(r2)
        }
        _ => false,
    }
}

/// Only patches that already agree on a primitive type (or one that fitted
/// nothing) may be trial-merged. A small plane tangent to a large cylinder does
/// sit inside the residual budget of that cylinder, so allowing cross-type
/// merges silently eats real planar faces.
fn mergeable_types(a: Prim, b: Prim) -> bool {
    matches!(a, Prim::Unknown) || matches!(b, Prim::Unknown) || a.name() == b.name()
}

/// A merge is only taken when the union fits as a primitive *everywhere*.
/// The area-weighted RMS alone lets a large well-fitting patch hide a small
/// one that has been dragged onto the wrong surface, which is how a chain of
/// greedy merges invents a shallow large-radius cylinder out of two planes.
fn accept_merge(f: Fit, p: &Params) -> bool {
    !matches!(f.prim, Prim::Unknown) && f.rms <= p.opts.tol && f.max_res <= 2.0 * p.opts.tol
}

/// Adjacent patch pairs, each listed once.
fn patch_pairs(mesh: &Mesh, label: &[usize]) -> Vec<(usize, usize)> {
    let mut seen: std::collections::HashSet<(usize, usize)> = std::collections::HashSet::new();
    for (i, nbrs) in mesh.neighbours.iter().enumerate() {
        let li = label[i];
        for &j in nbrs {
            let lj = label[j];
            if li != lj {
                seen.insert(if li < lj { (li, lj) } else { (lj, li) });
            }
        }
    }
    let mut out: Vec<(usize, usize)> = seen.into_iter().collect();
    out.sort_unstable();
    out
}

fn rebuild(label: &mut [usize], uf: &mut Uf, patches: &mut Vec<Vec<usize>>, fits: &mut Vec<Fit>) {
    let mut remap: HashMap<usize, usize> = HashMap::new();
    let mut new_patches: Vec<Vec<usize>> = Vec::new();
    let mut new_fits: Vec<Fit> = Vec::new();
    for old in 0..patches.len() {
        let root = uf.find(old);
        if let Some(&idx) = remap.get(&root) {
            let taken = std::mem::take(&mut patches[old]);
            new_patches[idx].extend(taken);
        } else {
            let idx = new_patches.len();
            remap.insert(root, idx);
            new_patches.push(std::mem::take(&mut patches[old]));
            new_fits.push(fits.get(root).copied().unwrap_or(Fit::UNKNOWN));
        }
    }
    for (idx, faces) in new_patches.iter().enumerate() {
        for &f in faces {
            label[f] = idx;
        }
    }
    *patches = new_patches;
    *fits = new_fits;
}

/// Face-level score against a candidate primitive: surface distance at the
/// triangle's vertices plus its normal deviation scaled to a length.
fn face_score(mesh: &Mesh, fi: usize, prim: Prim) -> f64 {
    let Some(face) = mesh.faces.get(fi) else {
        return f64::INFINITY;
    };
    if matches!(prim, Prim::Unknown) {
        return f64::INFINITY;
    }
    let mut dist = 0.0;
    for v in face.v {
        let Some(&p) = mesh.verts.get(v as usize) else {
            return f64::INFINITY;
        };
        dist += prim.residual(p);
    }
    dist /= 3.0;
    let ang = prim
        .normal_at(face.centroid)
        .map_or(std::f64::consts::FRAC_PI_2, |n| {
            let a = angle_between(face.normal, n);
            a.min(std::f64::consts::PI - a)
        });
    ang.mul_add(face.area.sqrt(), dist)
}

/// Re-cut one patch at a tighter dihedral angle, using only its own faces.
fn split_patch(mesh: &Mesh, faces: &[usize], label: &[usize], angle: f64) -> Vec<Vec<usize>> {
    let own = label.get(faces[0]).copied().unwrap_or(usize::MAX);
    let local: HashMap<usize, usize> = faces.iter().enumerate().map(|(i, &f)| (f, i)).collect();
    let mut uf = Uf::new(faces.len());
    for (i, &f) in faces.iter().enumerate() {
        for &g in &mesh.neighbours[f] {
            if label.get(g).copied() != Some(own) {
                continue;
            }
            let Some(&j) = local.get(&g) else { continue };
            if j > i && angle_between(mesh.faces[f].normal, mesh.faces[g].normal) < angle {
                uf.union(i, j);
            }
        }
    }
    let mut groups: HashMap<usize, Vec<usize>> = HashMap::new();
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

pub fn run(mesh: &Mesh, p: &Params) -> (Segmentation, Timings) {
    let nf = mesh.faces.len();

    // ── stage 1: smooth over-segmentation ─────────────────────────
    let t = now();
    let mut uf = Uf::new(nf);
    for (i, nbrs) in mesh.neighbours.iter().enumerate() {
        for &j in nbrs {
            if j > i && angle_between(mesh.faces[i].normal, mesh.faces[j].normal) < p.angle_rad {
                uf.union(i, j);
            }
        }
    }
    let mut label = vec![0_usize; nf];
    let mut patches: Vec<Vec<usize>> = Vec::new();
    let mut index: HashMap<usize, usize> = HashMap::new();
    for f in 0..nf {
        let root = uf.find(f);
        let idx = *index.entry(root).or_insert_with(|| {
            patches.push(Vec::new());
            patches.len() - 1
        });
        label[f] = idx;
        patches[idx].push(f);
    }
    let stage1_ms = ms(t);

    // ── stage 2: fit every patch ──────────────────────────────────
    let t = now();
    let mut fits: Vec<Fit> = patches.iter().map(|f| fit_faces(mesh, f, p)).collect();

    // ── stage 2b: split patches that fitted nothing ───────────────
    //
    // A vertical fillet is tangent to the planes it joins, so a pure dihedral
    // threshold leaks plane -> fillet -> plane into one blob that fits no
    // primitive. Re-cut such a blob at a progressively tighter angle; stage 3
    // then re-joins the pieces that really do share a surface.
    let mut split_angle = p.angle_rad;
    for _ in 0..p.split_levels {
        if fits.iter().all(|f| !matches!(f.prim, Prim::Unknown)) {
            break;
        }
        // Keep tightening even when a level changes nothing: the leak may only
        // break at a threshold two levels down.
        split_angle = (split_angle / 3.0).max(0.5_f64.to_radians());
        let mut next: Vec<Vec<usize>> = Vec::new();
        let mut changed = false;
        for (i, faces) in patches.iter().enumerate() {
            if !matches!(fits[i].prim, Prim::Unknown) || faces.len() < 2 {
                next.push(faces.clone());
                continue;
            }
            let parts = split_patch(mesh, faces, &label, split_angle);
            if parts.len() > 1 {
                changed = true;
            }
            next.extend(parts);
        }
        if !changed {
            continue;
        }
        patches = next;
        for (idx, faces) in patches.iter().enumerate() {
            for &f in faces {
                label[f] = idx;
            }
        }
        fits = patches.iter().map(|f| fit_faces(mesh, f, p)).collect();
    }

    let stage2_ms = ms(t);

    // ── stage 3: merge patches whose primitives agree ─────────────
    let t = now();
    let mut merge_rounds = 0_usize;
    for _ in 0..p.max_merge_rounds {
        merge_rounds += 1;
        let pairs = patch_pairs(mesh, &label);
        // Rank: agreeing primitives first, then trial merges by fit quality.
        let mut cands: Vec<(f64, usize, usize)> = Vec::new();
        for &(a, b) in &pairs {
            if same_surface(fits[a].prim, fits[b].prim, p) {
                cands.push((-1.0, a, b));
                continue;
            }
            if !mergeable_types(fits[a].prim, fits[b].prim) {
                continue;
            }
            let mut faces = patches[a].clone();
            faces.extend_from_slice(&patches[b]);
            let f = fit_faces(mesh, &faces, p);
            if accept_merge(f, p) {
                cands.push((f.rms, a, b));
            }
        }
        if cands.is_empty() {
            break;
        }
        cands.sort_by(|x, y| x.0.total_cmp(&y.0));

        let mut round_uf = Uf::new(patches.len());
        let mut merged_faces: HashMap<usize, Vec<usize>> = HashMap::new();
        let mut changed = false;
        for (_, a, b) in cands {
            let (ra, rb) = (round_uf.find(a), round_uf.find(b));
            if ra == rb {
                continue;
            }
            let fa = merged_faces.get(&ra).unwrap_or(&patches[ra]);
            let fb = merged_faces.get(&rb).unwrap_or(&patches[rb]);
            let mut faces = fa.clone();
            faces.extend_from_slice(fb);
            let f = fit_faces(mesh, &faces, p);
            if !accept_merge(f, p) {
                continue;
            }
            round_uf.union(ra, rb);
            let root = round_uf.find(ra);
            merged_faces.remove(&ra);
            merged_faces.remove(&rb);
            merged_faces.insert(root, faces);
            let _ = f;
            changed = true;
        }
        if !changed {
            break;
        }
        rebuild(&mut label, &mut round_uf, &mut patches, &mut fits);
        for (i, faces) in patches.iter().enumerate() {
            fits[i] = fit_faces(mesh, faces, p);
        }
    }
    let stage3_ms = ms(t);

    // ── stage 4: boundary refinement + unknown absorption ─────────
    let t = now();
    for _ in 0..p.refine_rounds {
        let mut moves: Vec<(usize, usize)> = Vec::new();
        for i in 0..nf {
            let own = label[i];
            let own_score = face_score(mesh, i, fits[own].prim);
            let mut best = (own_score, own);
            for &j in &mesh.neighbours[i] {
                let lj = label[j];
                if lj == own {
                    continue;
                }
                let s = face_score(mesh, i, fits[lj].prim);
                if s < best.0 * 0.999 && s <= p.opts.tol {
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
            if patches[from].len() <= 1 {
                continue;
            }
            patches[from].retain(|&x| x != f);
            patches[to].push(f);
            label[f] = to;
        }
        for (i, faces) in patches.iter().enumerate() {
            fits[i] = fit_faces(mesh, faces, p);
        }
    }

    // Unknown patches that complete an adjacent primitive get absorbed by it.
    for _ in 0..2 {
        let pairs = patch_pairs(mesh, &label);
        let mut cands: Vec<(f64, usize, usize)> = Vec::new();
        for &(a, b) in &pairs {
            let a_unknown = matches!(fits[a].prim, Prim::Unknown);
            let b_unknown = matches!(fits[b].prim, Prim::Unknown);
            if a_unknown == b_unknown {
                continue;
            }
            let mut faces = patches[a].clone();
            faces.extend_from_slice(&patches[b]);
            let f = fit_faces(mesh, &faces, p);
            if accept_merge(f, p) {
                cands.push((f.rms, a, b));
            }
        }
        if cands.is_empty() {
            break;
        }
        cands.sort_by(|x, y| x.0.total_cmp(&y.0));
        let mut round_uf = Uf::new(patches.len());
        let mut changed = false;
        for (_, a, b) in cands {
            let (ra, rb) = (round_uf.find(a), round_uf.find(b));
            if ra == rb {
                continue;
            }
            round_uf.union(ra, rb);
            changed = true;
        }
        if !changed {
            break;
        }
        rebuild(&mut label, &mut round_uf, &mut patches, &mut fits);
        for (i, faces) in patches.iter().enumerate() {
            fits[i] = fit_faces(mesh, faces, p);
        }
    }

    // Stable ids: largest patch first.
    let mut order: Vec<usize> = (0..patches.len()).collect();
    let area = |faces: &Vec<usize>| -> f64 {
        faces.iter().filter_map(|&f| mesh.faces.get(f)).map(|f| f.area).sum()
    };
    order.sort_by(|&a, &b| area(&patches[b]).total_cmp(&area(&patches[a])));
    let new_patches: Vec<Vec<usize>> = order.iter().map(|&i| patches[i].clone()).collect();
    let new_fits: Vec<Fit> = order.iter().map(|&i| fits[i]).collect();
    for (idx, faces) in new_patches.iter().enumerate() {
        for &f in faces {
            label[f] = idx;
        }
    }
    let stage4_ms = ms(t);

    (
        Segmentation {
            patches: new_patches,
            fits: new_fits,
        },
        Timings {
            stage1_ms,
            stage2_ms,
            stage3_ms,
            stage4_ms,
            merge_rounds,
        },
    )
}
