//! Loop assembly: a patch's incident edges chained into oriented loops.
//!
//! Which loop is the outer one is deliberately not decided here — that needs
//! the face's surface parameterisation, which is the next rung's job. All this
//! stage reports is how many loops a patch has and whether they closed.

use std::collections::BTreeMap;

use super::{Edge, Loop, PatchLoops};

pub(super) fn assemble(edges: &[Edge], patch_count: usize) -> Vec<PatchLoops> {
    let mut by_patch: Vec<Vec<u32>> = vec![Vec::new(); patch_count];
    for e in edges {
        for p in [e.patches.0, e.patches.1] {
            if let Some(list) = by_patch.get_mut(p as usize)
                && !list.contains(&e.id)
            {
                list.push(e.id);
            }
        }
    }

    let mut out = Vec::with_capacity(patch_count);
    for (patch, incident) in by_patch.into_iter().enumerate() {
        let mut loops = Vec::new();

        // A ring edge is a closed loop on its own. This is how a full cylinder
        // or a bore keeps a valid boundary with no vertex anywhere on it.
        let mut open: Vec<u32> = Vec::new();
        for id in incident {
            match edges.get(id as usize).and_then(|e| e.vertices) {
                Some(_) => open.push(id),
                None => loops.push(Loop {
                    edges: vec![(id, true)],
                    closed: true,
                }),
            }
        }

        let mut at_vertex: BTreeMap<u32, Vec<u32>> = BTreeMap::new();
        for &id in &open {
            if let Some((a, b)) = edges.get(id as usize).and_then(|e| e.vertices) {
                at_vertex.entry(a).or_default().push(id);
                if b != a {
                    at_vertex.entry(b).or_default().push(id);
                }
            }
        }

        let mut used: BTreeMap<u32, bool> = open.iter().map(|&id| (id, false)).collect();
        for &seed in &open {
            if used.get(&seed).copied().unwrap_or(true) {
                continue;
            }
            let Some((first, second)) = edges.get(seed as usize).and_then(|e| e.vertices) else {
                continue;
            };
            used.insert(seed, true);
            let mut walk = vec![(seed, true)];
            let mut cur = second;
            let closed = loop {
                if cur == first {
                    break true;
                }
                let Some(cands) = at_vertex.get(&cur) else {
                    break false;
                };
                let Some(&next) = cands
                    .iter()
                    .find(|id| !used.get(id).copied().unwrap_or(true))
                else {
                    break false;
                };
                let Some((a, b)) = edges.get(next as usize).and_then(|e| e.vertices) else {
                    break false;
                };
                used.insert(next, true);
                let forward = a == cur;
                walk.push((next, forward));
                cur = if forward { b } else { a };
            };
            loops.push(Loop {
                edges: walk,
                closed,
            });
        }

        let open_loops = loops.iter().filter(|l| !l.closed).count();
        out.push(PatchLoops {
            patch: patch as u32,
            loops,
            open_loops,
        });
    }
    out
}
