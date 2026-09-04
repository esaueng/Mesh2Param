//! Corpus scoreboard: run the faceted tier and the segmentation stage over
//! every real-world sample mesh and compare the outcome against a committed
//! baseline.
//!
//! This is the only thing that says whether a change to the core, or a bump of
//! the kernel pin, is an improvement. It runs before any face construction work
//! precisely so the "before" numbers exist.
//!
//! ```text
//! cargo test -p mesh2param-core --test scoreboard -- --nocapture
//! MESH2PARAM_SCOREBOARD=full cargo test -p mesh2param-core --test scoreboard -- --nocapture
//! MESH2PARAM_SCOREBOARD_WRITE_BASELINE=1 cargo test -p mesh2param-core --test scoreboard
//! ```

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

use mesh2param_core::{
    CoreError, FacetedOptions, Inventory, MeshFormat, SegmentOptions, TopologyOptions,
    faceted_step, load_mesh, recover, segment,
};
use serde::{Deserialize, Serialize};

/// Meshes above this triangle count are skipped unless `MESH2PARAM_SCOREBOARD=full`.
/// Keeps the default run to a couple of minutes so it can sit in CI.
const SUBSET_MAX_TRIANGLES: usize = 30_000;

/// A mesh's `inventory_error` may not grow by more than this fraction against
/// the baseline. Recognition counts move by one or two when a fit is retuned;
/// a fifth of the error is a change of behaviour, not of numerics.
const MAX_INVENTORY_ERROR_GROWTH: f64 = 0.20;

/// A mesh's `closed_patch_fraction` may not fall further than this below the
/// baseline. Loop closure is the one topology number a face builder cannot
/// work around: a patch whose boundary does not close has no face.
const MAX_CLOSURE_DROP: f64 = 0.05;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct PartJson {
    slug: String,
    meshes: Vec<MeshEntry>,
    ground_truth: Option<GroundTruth>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct GroundTruth {
    surface_inventory: Option<Truth>,
    /// Faces lying on one analytic surface, counted once. This is the honest
    /// target: the segmenter grows connected patches and has no reason to
    /// reproduce an exporter's face splitting.
    surface_inventory_merged: Option<Truth>,
}

impl GroundTruth {
    /// The merged inventory when the audit wrote one, else the raw face counts.
    fn truth(&self) -> Option<(Truth, GroundTruthSource)> {
        self.surface_inventory_merged
            .map(|t| (t, GroundTruthSource::Merged))
            .or_else(|| {
                self.surface_inventory
                    .map(|t| (t, GroundTruthSource::SurfaceInventory))
            })
    }
}

/// Which `part.json` key a row was scored against.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
enum GroundTruthSource {
    /// `groundTruth.surfaceInventoryMerged`.
    Merged,
    /// `groundTruth.surfaceInventory`: per-face, used only when no merged
    /// inventory is present (a `part.json` written before the audit grew one).
    SurfaceInventory,
}

/// Surface counts to score against. Surfaces the segmenter has no primitive
/// for (b-splines above all) are absent on purpose: they are not scored.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
struct Truth {
    #[serde(default)]
    plane: u32,
    #[serde(default)]
    cylinder: u32,
    #[serde(default)]
    cone: u32,
    #[serde(default)]
    torus: u32,
    #[serde(default)]
    sphere: u32,
}

impl Truth {
    /// Total absolute miscount over the five recognised surface types.
    fn error_against(self, got: Inventory) -> u32 {
        u32::abs_diff(got.plane, self.plane)
            + u32::abs_diff(got.cylinder, self.cylinder)
            + u32::abs_diff(got.cone, self.cone)
            + u32::abs_diff(got.torus, self.torus)
            + u32::abs_diff(got.sphere, self.sphere)
    }
}

/// The segmentation half of a row.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Seg {
    /// Wall clock for the segmentation alone. Omitted from the baseline.
    #[serde(default, skip_serializing_if = "is_zero")]
    ms: f64,
    inventory: Inventory,
    unknown_area_fraction: f64,
    /// `None` when the part has no STEP ground truth.
    ground_truth: Option<Truth>,
    /// Which `part.json` inventory `ground_truth` came from; `None` exactly
    /// when `ground_truth` is.
    ground_truth_source: Option<GroundTruthSource>,
    /// `None` exactly when `ground_truth` is.
    inventory_error: Option<u32>,
}

/// The topology half of a row, measured after segmentation.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Topo {
    /// Wall clock for topology recovery alone. Omitted from the baseline.
    #[serde(default, skip_serializing_if = "is_zero")]
    ms: f64,
    edges: usize,
    /// Share of edges whose curve came from a real surface-surface
    /// intersection. Zero when there are no edges.
    analytic_fraction: f64,
    tangent_edges: usize,
    /// Share of patches all of whose loops closed.
    closed_patch_fraction: f64,
    max_edge_deviation: f64,
    /// `None` unless recovery itself failed, in which case every other field
    /// is zero.
    error: Option<String>,
}

impl Topo {
    fn failed(error: String) -> Self {
        Self {
            ms: 0.0,
            edges: 0,
            analytic_fraction: 0.0,
            tangent_edges: 0,
            closed_patch_fraction: 0.0,
            max_edge_deviation: 0.0,
            error: Some(error),
        }
    }
}

#[derive(Debug, Deserialize)]
struct MeshEntry {
    file: String,
    triangles: usize,
}

/// One scoreboard row. `ms` is measured, not compared.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Row {
    slug: String,
    mesh: String,
    triangles: usize,
    tier: Option<String>,
    valid: bool,
    faces_imported: u64,
    faces_unified: u64,
    /// Wall clock for load + reconstruct. Omitted from the baseline, which
    /// must not change when the machine running it does.
    #[serde(default, skip_serializing_if = "is_zero")]
    ms: f64,
    error: Option<String>,
    /// `None` when segmentation itself failed; `segError` then says why. Kept
    /// out of `error`, which stays the faceted tier's own outcome.
    segmentation: Option<Seg>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    seg_error: Option<String>,
    /// `None` when segmentation never produced patches to recover from.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    topology: Option<Topo>,
}

#[allow(clippy::trivially_copy_pass_by_ref)] // serde requires the &T signature
fn is_zero(v: &f64) -> bool {
    v.abs() < f64::EPSILON
}

impl Row {
    fn key(&self) -> String {
        format!("{}/{}", self.slug, self.mesh)
    }

    /// The comparable half of a row: the baseline deliberately does not carry
    /// timings, so a slower machine is never a failure.
    fn without_timing(&self) -> Self {
        Self {
            ms: 0.0,
            segmentation: self.segmentation.as_ref().map(|s| Seg {
                ms: 0.0,
                ..s.clone()
            }),
            topology: self.topology.as_ref().map(|t| Topo {
                ms: 0.0,
                ..t.clone()
            }),
            ..self.clone()
        }
    }

    fn closed_patch_fraction(&self) -> Option<f64> {
        self.topology
            .as_ref()
            .filter(|t| t.error.is_none())
            .map(|t| t.closed_patch_fraction)
    }

    fn inventory_error(&self) -> Option<u32> {
        self.segmentation.as_ref().and_then(|s| s.inventory_error)
    }
}

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .expect("repo root resolves from CARGO_MANIFEST_DIR")
}

fn part_files(corpus: &Path) -> Vec<PathBuf> {
    let mut parts: Vec<PathBuf> = fs::read_dir(corpus)
        .unwrap_or_else(|e| panic!("read {}: {e}", corpus.display()))
        .filter_map(Result::ok)
        .map(|e| e.path().join("part.json"))
        .filter(|p| p.is_file())
        .collect();
    parts.sort();
    parts
}

fn run_one(
    dir: &Path,
    slug: &str,
    entry: &MeshEntry,
    truth: Option<(Truth, GroundTruthSource)>,
) -> Option<Row> {
    let stl = dir.join(&entry.file);
    // mesh-fine.stl is opt-in and not committed; a missing file is not a failure.
    if !stl.is_file() {
        return None;
    }
    let mesh_name = entry
        .file
        .strip_suffix(".stl")
        .unwrap_or(&entry.file)
        .to_string();

    let mut row = Row {
        slug: slug.to_string(),
        mesh: mesh_name,
        triangles: entry.triangles,
        tier: None,
        valid: false,
        faces_imported: 0,
        faces_unified: 0,
        ms: 0.0,
        error: None,
        segmentation: None,
        seg_error: None,
        topology: None,
    };

    let bytes = match fs::read(&stl) {
        Ok(b) => b,
        Err(e) => {
            row.error = Some(format!("read: {e}"));
            return Some(row);
        }
    };

    let started = Instant::now();
    let loaded = load_mesh(&bytes, MeshFormat::Stl);
    let outcome = loaded
        .as_ref()
        .map_err(short)
        .and_then(|mesh| faceted_step(mesh, &FacetedOptions::default()).map_err(|e| short(&e)));
    row.ms = started.elapsed().as_secs_f64() * 1000.0;

    let mut segmentation = None;
    if let Ok(mesh) = &loaded {
        let started = Instant::now();
        match segment(mesh, &SegmentOptions::default()) {
            Ok(seg) => {
                row.segmentation = Some(Seg {
                    ms: started.elapsed().as_secs_f64() * 1000.0,
                    inventory: seg.inventory,
                    unknown_area_fraction: seg.unknown_area_fraction,
                    ground_truth: truth.map(|(t, _)| t),
                    ground_truth_source: truth.map(|(_, source)| source),
                    inventory_error: truth.map(|(t, _)| t.error_against(seg.inventory)),
                });
                segmentation = Some(seg);
            }
            Err(e) => row.seg_error = Some(short(&e)),
        }
    }

    if let (Ok(mesh), Some(seg)) = (&loaded, &segmentation) {
        let started = Instant::now();
        row.topology = Some(match recover(mesh, seg, &TopologyOptions::default()) {
            Ok(topo) => {
                let s = topo.summary;
                let patches = s.patches_closed + s.patches_open;
                Topo {
                    ms: started.elapsed().as_secs_f64() * 1000.0,
                    edges: s.edges,
                    analytic_fraction: if s.edges == 0 {
                        0.0
                    } else {
                        s.analytic_edges as f64 / s.edges as f64
                    },
                    tangent_edges: s.tangent_edges,
                    closed_patch_fraction: if patches == 0 {
                        0.0
                    } else {
                        s.patches_closed as f64 / patches as f64
                    },
                    max_edge_deviation: s.max_edge_deviation,
                    error: None,
                }
            }
            Err(e) => Topo::failed(short(&e)),
        });
    }

    match outcome {
        Ok(result) => {
            row.tier = Some(
                serde_json::to_value(result.tier)
                    .unwrap()
                    .as_str()
                    .unwrap()
                    .to_string(),
            );
            row.valid = result.valid;
            row.faces_imported = result.faces_imported;
            row.faces_unified = result.faces_unified;
        }
        Err(e) => row.error = Some(e),
    }
    Some(row)
}

/// Errors are compared across runs, so they must be stable text: strip the
/// variable tail (counts, ids) by keeping only the first 120 characters.
fn short(e: &CoreError) -> String {
    let one = e.to_string().replace('\n', " ");
    if one.chars().count() > 120 {
        one.chars().take(117).collect::<String>() + "..."
    } else {
        one
    }
}

fn print_table(rows: &[Row]) {
    println!(
        "\n{:<26} {:<16} {:>7} {:>7} {:>5} {:>8} | {:>8} {:>4} {:>4} {:>4} {:>4} {:>4} {:>4} {:>7} {:>6} | {:>7} {:>6} {:>6} {:>4} {:>6} {:>8}  notes",
        "slug",
        "mesh",
        "tris",
        "unified",
        "valid",
        "ms",
        "seg ms",
        "pl",
        "cy",
        "co",
        "to",
        "sp",
        "unk",
        "unkArea",
        "invErr",
        "topo ms",
        "edges",
        "anaFr",
        "tan",
        "closed",
        "maxDev"
    );
    println!("{}", "-".repeat(210));
    for r in rows {
        let (seg_ms, inv, unk, err) = r.segmentation.as_ref().map_or_else(
            || (f64::NAN, Inventory::default(), f64::NAN, None),
            |s| {
                (
                    s.ms,
                    s.inventory,
                    s.unknown_area_fraction,
                    s.inventory_error,
                )
            },
        );
        let topo = r.topology.as_ref();
        let mut notes = match (r.error.as_deref(), r.seg_error.as_deref()) {
            (Some(e), Some(s)) => format!("{e} | seg: {s}"),
            (Some(e), None) => e.to_string(),
            (None, Some(s)) => format!("seg: {s}"),
            (None, None) => String::new(),
        };
        if let Some(e) = topo.and_then(|t| t.error.as_deref()) {
            if !notes.is_empty() {
                notes.push_str(" | ");
            }
            notes.push_str("topo: ");
            notes.push_str(e);
        }
        println!(
            "{:<26} {:<16} {:>7} {:>7} {:>5} {:>8.1} | {:>8.1} {:>4} {:>4} {:>4} {:>4} {:>4} {:>4} {:>7.3} {:>6} | {:>7.1} {:>6} {:>6.3} {:>4} {:>6.3} {:>8.4}  {}",
            r.slug,
            r.mesh,
            r.triangles,
            r.faces_unified,
            if r.valid { "yes" } else { "no" },
            r.ms,
            seg_ms,
            inv.plane,
            inv.cylinder,
            inv.cone,
            inv.torus,
            inv.sphere,
            inv.unknown,
            unk,
            err.map_or_else(|| "-".to_string(), |e| e.to_string()),
            topo.map_or(f64::NAN, |t| t.ms),
            topo.map_or(0, |t| t.edges),
            topo.map_or(f64::NAN, |t| t.analytic_fraction),
            topo.map_or(0, |t| t.tangent_edges),
            topo.map_or(f64::NAN, |t| t.closed_patch_fraction),
            topo.map_or(f64::NAN, |t| t.max_edge_deviation),
            notes
        );
    }
    let valid = rows.iter().filter(|r| r.valid).count();
    let errored = rows.iter().filter(|r| r.error.is_some()).count();
    let scored: Vec<u32> = rows.iter().filter_map(Row::inventory_error).collect();
    let mean_err = if scored.is_empty() {
        0.0
    } else {
        f64::from(scored.iter().sum::<u32>()) / scored.len() as f64
    };
    let closure: Vec<f64> = rows.iter().filter_map(Row::closed_patch_fraction).collect();
    let analytic: Vec<f64> = rows
        .iter()
        .filter_map(|r| r.topology.as_ref())
        .filter(|t| t.error.is_none() && t.edges > 0)
        .map(|t| t.analytic_fraction)
        .collect();
    let tangent: usize = rows
        .iter()
        .filter_map(|r| r.topology.as_ref())
        .map(|t| t.tangent_edges)
        .sum();
    let mean = |v: &[f64]| -> f64 {
        if v.is_empty() {
            0.0
        } else {
            v.iter().sum::<f64>() / v.len() as f64
        }
    };
    println!(
        "{}\n{} meshes, {} valid, {} errored; {} scored against STEP ground truth, mean inventory error {:.1}\ntopology: {} recovered, mean closed patch fraction {:.3}, mean analytic edge fraction {:.3}, {} tangent edges\n",
        "-".repeat(210),
        rows.len(),
        valid,
        errored,
        scored.len(),
        mean_err,
        closure.len(),
        mean(&closure),
        mean(&analytic),
        tangent
    );
}

#[test]
fn corpus_scoreboard_matches_baseline() {
    let root = repo_root();
    let corpus = root.join("samples/real");
    let full = std::env::var("MESH2PARAM_SCOREBOARD").as_deref() == Ok("full");

    let mut rows = Vec::new();
    for part_file in part_files(&corpus) {
        let dir = part_file.parent().unwrap().to_path_buf();
        let text = fs::read_to_string(&part_file)
            .unwrap_or_else(|e| panic!("read {}: {e}", part_file.display()));
        let part: PartJson = serde_json::from_str(&text)
            .unwrap_or_else(|e| panic!("parse {}: {e}", part_file.display()));
        let truth = part.ground_truth.as_ref().and_then(GroundTruth::truth);
        for entry in &part.meshes {
            if !full && entry.triangles > SUBSET_MAX_TRIANGLES {
                continue;
            }
            if let Some(row) = run_one(&dir, &part.slug, entry, truth) {
                rows.push(row);
            }
        }
    }
    assert!(
        !rows.is_empty(),
        "no corpus meshes found under {}",
        corpus.display()
    );
    rows.sort_by_key(Row::key);
    print_table(&rows);

    let out_dir = root.join("target");
    fs::create_dir_all(&out_dir).unwrap();
    fs::write(
        out_dir.join("scoreboard.json"),
        serde_json::to_string_pretty(&rows).unwrap(),
    )
    .unwrap();

    let baseline_path = Path::new(env!("CARGO_MANIFEST_DIR")).join("scoreboard-baseline.json");
    if std::env::var("MESH2PARAM_SCOREBOARD_WRITE_BASELINE").is_ok() {
        let stripped: Vec<Row> = rows.iter().map(Row::without_timing).collect();
        fs::write(
            &baseline_path,
            serde_json::to_string_pretty(&stripped).unwrap() + "\n",
        )
        .unwrap();
        println!("wrote baseline {}", baseline_path.display());
        return;
    }

    let baseline_text = fs::read_to_string(&baseline_path)
        .unwrap_or_else(|e| panic!("read {}: {e}", baseline_path.display()));
    let baseline: Vec<Row> = serde_json::from_str(&baseline_text).unwrap();
    let baseline: BTreeMap<String, Row> = baseline.into_iter().map(|r| (r.key(), r)).collect();

    let mut regressions = Vec::new();
    let mut new_meshes = Vec::new();
    let mut improvements = Vec::new();
    for row in &rows {
        let Some(before) = baseline.get(&row.key()) else {
            new_meshes.push(row.key());
            continue;
        };
        if before.valid && !row.valid {
            regressions.push(format!(
                "{}: was valid, now invalid (error: {})",
                row.key(),
                row.error.as_deref().unwrap_or("none")
            ));
        }
        if before.error.is_none() && row.error.is_some() {
            regressions.push(format!(
                "{}: now errors: {}",
                row.key(),
                row.error.as_deref().unwrap_or("")
            ));
        }
        if !before.valid && row.valid {
            improvements.push(row.key());
        }
        // Recognition regressions are counted separately from the faceted
        // tier's: a mesh can still build a valid solid while the segmenter has
        // started reporting the wrong surfaces.
        if let (Some(was), Some(now)) = (before.inventory_error(), row.inventory_error()) {
            if f64::from(now) > f64::from(was) * (1.0 + MAX_INVENTORY_ERROR_GROWTH) {
                regressions.push(format!(
                    "{}: inventory error {was} -> {now}, over the {:.0}% growth budget",
                    row.key(),
                    MAX_INVENTORY_ERROR_GROWTH * 100.0
                ));
            } else if now < was {
                improvements.push(format!("{}: inventory error {was} -> {now}", row.key()));
            }
        }
        // Loop closure is scored separately again: a mesh can keep its
        // recognition and still stop producing usable face boundaries.
        if let (Some(was), Some(now)) =
            (before.closed_patch_fraction(), row.closed_patch_fraction())
            && now < was - MAX_CLOSURE_DROP
        {
            regressions.push(format!(
                "{}: closed patch fraction {was:.3} -> {now:.3}, past the {MAX_CLOSURE_DROP:.2} drop budget",
                row.key()
            ));
        }
        if before.topology.as_ref().is_some_and(|t| t.error.is_none())
            && row.topology.as_ref().is_some_and(|t| t.error.is_some())
        {
            regressions.push(format!(
                "{}: topology now errors: {}",
                row.key(),
                row.topology
                    .as_ref()
                    .and_then(|t| t.error.as_deref())
                    .unwrap_or("")
            ));
        }
    }
    // A mesh present in the baseline but absent now means the corpus shrank or
    // a file stopped being read: worth failing on, not silently passing.
    for key in baseline.keys() {
        if !rows.iter().any(|r| &r.key() == key) {
            regressions.push(format!("{key}: in baseline but not produced by this run"));
        }
    }

    if !new_meshes.is_empty() {
        println!("new meshes not in the baseline ({}):", new_meshes.len());
        for k in &new_meshes {
            println!("  + {k}");
        }
    }
    if !improvements.is_empty() {
        println!("improvements ({}):", improvements.len());
        for k in &improvements {
            println!("  ^ {k}");
        }
    }
    assert!(
        regressions.is_empty(),
        "scoreboard regressed against {}:\n  {}",
        baseline_path.display(),
        regressions.join("\n  ")
    );
}
