//! Corpus scoreboard: run the faceted tier over every real-world sample mesh
//! and compare the outcome against a committed baseline.
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

use mesh2param_core::{CoreError, FacetedOptions, MeshFormat, faceted_step, load_mesh};
use serde::{Deserialize, Serialize};

/// Meshes above this triangle count are skipped unless `MESH2PARAM_SCOREBOARD=full`.
/// Keeps the default run to a couple of minutes so it can sit in CI.
const SUBSET_MAX_TRIANGLES: usize = 30_000;

#[derive(Debug, Deserialize)]
struct PartJson {
    slug: String,
    meshes: Vec<MeshEntry>,
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
            ..self.clone()
        }
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

fn run_one(dir: &Path, slug: &str, entry: &MeshEntry) -> Option<Row> {
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
    };

    let bytes = match fs::read(&stl) {
        Ok(b) => b,
        Err(e) => {
            row.error = Some(format!("read: {e}"));
            return Some(row);
        }
    };

    let started = Instant::now();
    let outcome = load_mesh(&bytes, MeshFormat::Stl)
        .and_then(|mesh| faceted_step(&mesh, &FacetedOptions::default()));
    row.ms = started.elapsed().as_secs_f64() * 1000.0;

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
        Err(e) => row.error = Some(short(&e)),
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
        "\n{:<28} {:<18} {:>8} {:>8} {:>8} {:>6} {:>9}  error",
        "slug", "mesh", "tris", "faces", "unified", "valid", "ms"
    );
    println!("{}", "-".repeat(110));
    for r in rows {
        println!(
            "{:<28} {:<18} {:>8} {:>8} {:>8} {:>6} {:>9.1}  {}",
            r.slug,
            r.mesh,
            r.triangles,
            r.faces_imported,
            r.faces_unified,
            if r.valid { "yes" } else { "no" },
            r.ms,
            r.error.as_deref().unwrap_or("")
        );
    }
    let valid = rows.iter().filter(|r| r.valid).count();
    let errored = rows.iter().filter(|r| r.error.is_some()).count();
    println!(
        "{}\n{} meshes, {} valid, {} errored\n",
        "-".repeat(110),
        rows.len(),
        valid,
        errored
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
        for entry in &part.meshes {
            if !full && entry.triangles > SUBSET_MAX_TRIANGLES {
                continue;
            }
            if let Some(row) = run_one(&dir, &part.slug, entry) {
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
        println!("improved to valid ({}):", improvements.len());
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
