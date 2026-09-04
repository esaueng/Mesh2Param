//! Patch adjacency and boundary chains.
//!
//! A mesh edge whose owning triangles do not all belong to one patch is a
//! boundary edge. Boundary edges are grouped by the unordered patch pair they
//! separate and linked into ordered vertex chains; a chain ends at a vertex
//! that touches three or more patches (a corner) or where the pair's own edge
//! graph branches, and closes into a ring when it meets neither.
//!
//! Everything here is driven by `BTreeMap`/`BTreeSet`, never a hash map:
//! traversal order decides chain order, which decides edge ids, which end up
//! in a committed baseline.

use std::collections::{BTreeMap, BTreeSet};

use crate::mesh::WeldedMesh;

/// One boundary chain: an ordered run of mesh vertices separating two patches.
pub(super) struct Chain {
    /// The two patches, ascending.
    pub patches: (u32, u32),
    /// Mesh vertex indices in order. A ring does not repeat its first vertex.
    pub verts: Vec<u32>,
    /// Whether the chain closes on itself with no vertex on it.
    pub closed: bool,
}

/// What [`build`] found.
pub(super) struct Adjacency {
    /// The chains, ordered by patch pair then by discovery.
    pub chains: Vec<Chain>,
    /// Patches incident to each mesh vertex.
    pub vertex_patches: Vec<BTreeSet<u32>>,
}

fn key(a: u32, b: u32) -> (u32, u32) {
    if a < b { (a, b) } else { (b, a) }
}

pub(super) fn build(welded: &WeldedMesh, face_patch: &[u32], patch_count: usize) -> Adjacency {
    let mut vertex_patches: Vec<BTreeSet<u32>> = vec![BTreeSet::new(); welded.positions.len()];
    for (fi, tri) in welded.triangles.iter().enumerate() {
        let Some(&patch) = face_patch.get(fi) else {
            continue;
        };
        if patch as usize >= patch_count {
            continue;
        }
        for &v in tri {
            if let Some(set) = vertex_patches.get_mut(v as usize) {
                set.insert(patch);
            }
        }
    }

    // Mesh edge -> the distinct patches of its owning triangles.
    let mut edge_patches: BTreeMap<(u32, u32), BTreeSet<u32>> = BTreeMap::new();
    for (fi, tri) in welded.triangles.iter().enumerate() {
        let Some(&patch) = face_patch.get(fi) else {
            continue;
        };
        for k in 0..3 {
            let e = key(tri[k], tri[(k + 1) % 3]);
            edge_patches.entry(e).or_default().insert(patch);
        }
    }

    // Only a clean two-patch edge is a usable boundary. An edge with three or
    // more patches on it is a non-manifold seam: its endpoints are corners
    // anyway, and forcing it into a pair would invent a chain that no pair of
    // surfaces actually meets along.
    let mut pair_edges: BTreeMap<(u32, u32), Vec<(u32, u32)>> = BTreeMap::new();
    for (edge, patches) in &edge_patches {
        if patches.len() != 2 {
            continue;
        }
        let mut it = patches.iter();
        let (Some(&a), Some(&b)) = (it.next(), it.next()) else {
            continue;
        };
        pair_edges.entry((a, b)).or_default().push(*edge);
    }

    let junction =
        |v: u32| -> bool { vertex_patches.get(v as usize).is_some_and(|s| s.len() >= 3) };

    let mut chains = Vec::new();
    for (patches, edges) in &pair_edges {
        let mut incident: BTreeMap<u32, Vec<usize>> = BTreeMap::new();
        for (i, &(a, b)) in edges.iter().enumerate() {
            incident.entry(a).or_default().push(i);
            incident.entry(b).or_default().push(i);
        }
        let is_break =
            |v: u32| -> bool { junction(v) || incident.get(&v).is_none_or(|l| l.len() != 2) };

        let mut used = vec![false; edges.len()];
        let other = |ei: usize, v: u32| -> u32 {
            let (a, b) = edges[ei];
            if a == v { b } else { a }
        };

        // Open chains first, walked from every breakpoint.
        for (&v, list) in &incident {
            if !is_break(v) {
                continue;
            }
            for &start_edge in list {
                if used[start_edge] {
                    continue;
                }
                let mut verts = vec![v];
                let mut ei = start_edge;
                let mut cur = v;
                loop {
                    used[ei] = true;
                    let next = other(ei, cur);
                    verts.push(next);
                    cur = next;
                    if is_break(cur) {
                        break;
                    }
                    let Some(cands) = incident.get(&cur) else {
                        break;
                    };
                    let Some(&nxt) = cands.iter().find(|&&e| !used[e]) else {
                        break;
                    };
                    ei = nxt;
                }
                chains.push(Chain {
                    patches: *patches,
                    verts,
                    closed: false,
                });
            }
        }

        // Whatever is left is a ring: no vertex on it branches or corners.
        for start_edge in 0..edges.len() {
            if used[start_edge] {
                continue;
            }
            let (a, _) = edges[start_edge];
            let mut verts = vec![a];
            let mut ei = start_edge;
            let mut cur = a;
            loop {
                used[ei] = true;
                let next = other(ei, cur);
                cur = next;
                if cur == a {
                    break;
                }
                verts.push(cur);
                let Some(cands) = incident.get(&cur) else {
                    break;
                };
                let Some(&nxt) = cands.iter().find(|&&e| !used[e]) else {
                    break;
                };
                ei = nxt;
            }
            chains.push(Chain {
                patches: *patches,
                verts,
                closed: true,
            });
        }
    }

    Adjacency {
        chains,
        vertex_patches,
    }
}
