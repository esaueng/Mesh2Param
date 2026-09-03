//! Segmentation spike: recover the analytic surface inventory of a real part
//! from its triangle mesh by region growing with primitive refit.
//!
//! ```text
//! segmentation --stl <path> --out <dir> [--angle-deg 12] [--tol-frac 0.002]
//! ```
//!
//! One mesh per process. Exactly one JSON object goes to stdout; every failure
//! mode (bad path, unreadable STL, panic in a fit) becomes a JSON `error`
//! rather than a crash, so a corpus run always gets a record per part.

// Spike code: small maths bindings (n, d, r, c) and long straight-line stage
// drivers are clearer here than the pedantic-lint-friendly alternatives.
#![allow(
    clippy::many_single_char_names,
    clippy::similar_names,
    clippy::too_many_lines,
    clippy::needless_range_loop
)]

mod fit;
mod linalg;
mod mesh;
mod ply;
mod seg;

use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::PathBuf;
use std::time::Instant;

use fit::{FitOpts, Prim};
use linalg::V3;
use mesh::Mesh;
use serde_json::{Map, Value, json};

struct Args {
    stl: PathBuf,
    out: PathBuf,
    angle_deg: f64,
    tol_frac: f64,
    min_spread_deg: f64,
    max_facet_deg: f64,
    max_normal_dev_deg: f64,
    radius_tol_frac: f64,
    merge_rounds: usize,
    refine_rounds: usize,
    split_levels: usize,
    fit_on_centroids: bool,
}

fn parse_args() -> Result<Args, String> {
    let (mut stl, mut out) = (None, None);
    let mut a = Args {
        stl: PathBuf::new(),
        out: PathBuf::new(),
        angle_deg: 12.0,
        tol_frac: 0.002,
        min_spread_deg: 8.0,
        max_facet_deg: 40.0,
        max_normal_dev_deg: 12.0,
        radius_tol_frac: 0.002,
        merge_rounds: 12,
        refine_rounds: 2,
        split_levels: 3,
        fit_on_centroids: false,
    };
    let mut it = std::env::args().skip(1);
    let num = |v: Option<String>, name: &str| -> Result<f64, String> {
        v.ok_or_else(|| format!("{name} needs a number"))?
            .parse::<f64>()
            .map_err(|e| format!("{name}: {e}"))
    };
    while let Some(arg) = it.next() {
        match arg.as_str() {
            "--stl" => stl = it.next().map(PathBuf::from),
            "--out" => out = it.next().map(PathBuf::from),
            "--angle-deg" => a.angle_deg = num(it.next(), "--angle-deg")?,
            "--tol-frac" => a.tol_frac = num(it.next(), "--tol-frac")?,
            "--min-spread-deg" => a.min_spread_deg = num(it.next(), "--min-spread-deg")?,
            "--max-facet-deg" => a.max_facet_deg = num(it.next(), "--max-facet-deg")?,
            "--radius-tol-frac" => a.radius_tol_frac = num(it.next(), "--radius-tol-frac")?,
            "--max-normal-dev-deg" => {
                a.max_normal_dev_deg = num(it.next(), "--max-normal-dev-deg")?;
            }
            #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
            "--merge-rounds" => a.merge_rounds = num(it.next(), "--merge-rounds")?.max(0.0) as usize,
            #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
            "--refine-rounds" => {
                a.refine_rounds = num(it.next(), "--refine-rounds")?.max(0.0) as usize;
            }
            #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
            "--split-levels" => {
                a.split_levels = num(it.next(), "--split-levels")?.max(0.0) as usize;
            }
            "--fit-on" => {
                a.fit_on_centroids = match it.next().as_deref() {
                    Some("centroids") => true,
                    Some("vertices") => false,
                    other => return Err(format!("--fit-on wants vertices|centroids, got {other:?}")),
                };
            }
            other => return Err(format!("unknown argument {other}")),
        }
    }
    a.stl = stl.ok_or("missing --stl")?;
    a.out = out.ok_or("missing --out")?;
    Ok(a)
}

fn v3(v: V3) -> Value {
    json!([v.x, v.y, v.z])
}

fn stem(path: &std::path::Path) -> String {
    path.file_stem()
        .map_or_else(|| "mesh".to_string(), |s| s.to_string_lossy().to_string())
}

fn run(args: &Args) -> Result<Value, String> {
    let t_all = Instant::now();

    let t = Instant::now();
    let bytes = std::fs::read(&args.stl).map_err(|e| format!("read {}: {e}", args.stl.display()))?;
    let raw = remus_io::stl::reader::read_stl_with_limits(&bytes, remus_io::ImportLimits::default())
        .map_err(|e| format!("read_stl: {e}"))?;
    let read_ms = t.elapsed().as_secs_f64() * 1000.0;

    let t = Instant::now();
    let positions: Vec<V3> = raw
        .positions
        .iter()
        .map(|p| V3::new(p.0[0], p.0[1], p.0[2]))
        .collect();
    let m = Mesh::build(&positions, &raw.indices)?;
    let build_ms = t.elapsed().as_secs_f64() * 1000.0;

    let params = seg::Params {
        angle_rad: args.angle_deg.to_radians(),
        opts: FitOpts {
            tol: args.tol_frac * m.bbox_diag,
            min_spread: args.min_spread_deg.to_radians(),
            max_facet_step: args.max_facet_deg.to_radians(),
            max_normal_dev: args.max_normal_dev_deg.to_radians(),
            radius_tol_frac: args.radius_tol_frac,
            bbox_diag: m.bbox_diag,
        },
        merge_angle_rad: 1.0_f64.to_radians(),
        merge_radius_frac: 0.01,
        max_merge_rounds: args.merge_rounds,
        refine_rounds: args.refine_rounds,
        split_levels: args.split_levels,
        fit_on_centroids: args.fit_on_centroids,
    };
    let (segs, timings) = seg::run(&m, &params);

    let t = Instant::now();
    let total_area: f64 = m.faces.iter().map(|f| f.area).sum();
    let mut inventory: Map<String, Value> = Map::new();
    for k in ["plane", "cylinder", "sphere", "unknown"] {
        inventory.insert(k.to_string(), json!(0));
    }
    let mut unknown_area = 0.0;
    let mut patches_json: Vec<Value> = Vec::with_capacity(segs.patches.len());
    let mut colours: Vec<[u8; 3]> = vec![[130, 130, 130]; m.faces.len()];

    for (id, faces) in segs.patches.iter().enumerate() {
        let f = segs.fits[id];
        let area: f64 = faces.iter().filter_map(|&i| m.faces.get(i)).map(|x| x.area).sum();
        let name = f.prim.name();
        let known = name != "unknown";
        if !known {
            unknown_area += area;
        }
        let slot = inventory.entry(name.to_string()).or_insert(json!(0));
        let prev = slot.as_u64().unwrap_or(0);
        *slot = json!(prev + 1);

        let colour = ply::patch_colour(id, known);
        for &i in faces {
            if let Some(c) = colours.get_mut(i) {
                *c = colour;
            }
        }

        let mut obj = Map::new();
        obj.insert("id".into(), json!(id));
        obj.insert("type".into(), json!(name));
        obj.insert("faces".into(), json!(faces.len()));
        obj.insert("area".into(), json!(area));
        obj.insert(
            "rmsResidual".into(),
            if f.rms.is_finite() { json!(f.rms) } else { Value::Null },
        );
        obj.insert(
            "maxResidual".into(),
            if f.max_res.is_finite() { json!(f.max_res) } else { Value::Null },
        );
        match f.prim {
            Prim::Plane { n, d } => {
                obj.insert("plane".into(), json!({"normal": v3(n), "d": d}));
            }
            Prim::Cylinder { p, dir, r, sweep_deg } => {
                obj.insert(
                    "cylinder".into(),
                    json!({"axisPoint": v3(p), "axisDir": v3(dir), "radius": r, "sweepDeg": sweep_deg}),
                );
            }
            Prim::Sphere { c, r } => {
                obj.insert("sphere".into(), json!({"center": v3(c), "radius": r}));
            }
            Prim::Unknown => {}
        }
        patches_json.push(Value::Object(obj));
    }

    std::fs::create_dir_all(&args.out).map_err(|e| format!("mkdir {}: {e}", args.out.display()))?;
    let base = stem(&args.stl);
    let ply_path = args.out.join(format!("{base}.segments.ply"));
    ply::write(&ply_path, &m, &colours)?;
    let output_ms = t.elapsed().as_secs_f64() * 1000.0;

    Ok(json!({
        "stl": args.stl.to_string_lossy(),
        "triangles": m.faces.len(),
        "rawTriangles": m.raw_triangles,
        "weldedVertices": m.verts.len(),
        "nonManifoldEdges": m.non_manifold_edges,
        "bboxDiagonal": m.bbox_diag,
        "params": {
            "angleDeg": args.angle_deg,
            "tolFrac": args.tol_frac,
            "tolAbs": params.opts.tol,
            "minSpreadDeg": args.min_spread_deg,
            "maxFacetDeg": args.max_facet_deg,
            "maxNormalDevDeg": args.max_normal_dev_deg,
            "radiusTolFrac": args.radius_tol_frac,
            "mergeRounds": args.merge_rounds,
            "refineRounds": args.refine_rounds,
            "splitLevels": args.split_levels,
            "fitOn": if args.fit_on_centroids { "centroids" } else { "vertices" },
        },
        "patches": patches_json,
        "inventory": Value::Object(inventory),
        "unknownAreaFraction": if total_area > 0.0 { unknown_area / total_area } else { 0.0 },
        "plyPath": ply_path.to_string_lossy(),
        "timings": {
            "readMs": read_ms,
            "buildMs": build_ms,
            "stage1Ms": timings.stage1_ms,
            "stage2Ms": timings.stage2_ms,
            "stage3Ms": timings.stage3_ms,
            "stage4Ms": timings.stage4_ms,
            "outputMs": output_ms,
            "mergeRoundsRun": timings.merge_rounds,
            "totalMs": t_all.elapsed().as_secs_f64() * 1000.0,
        },
    }))
}

fn main() {
    let result = catch_unwind(AssertUnwindSafe(|| parse_args().and_then(|a| run(&a))));
    let value = match result {
        Ok(Ok(v)) => v,
        Ok(Err(e)) => json!({"error": e}),
        Err(p) => {
            let msg = p
                .downcast_ref::<&str>()
                .map(|s| (*s).to_string())
                .or_else(|| p.downcast_ref::<String>().cloned())
                .unwrap_or_else(|| "unknown".into());
            json!({"error": format!("panic: {msg}")})
        }
    };
    let failed = value.get("error").is_some();
    // Also persist the JSON next to the PLY when the run produced one.
    if let (Some(Value::String(ply)), Ok(text)) =
        (value.get("plyPath"), serde_json::to_string_pretty(&value))
    {
        let json_path = ply.replace(".segments.ply", ".segments.json");
        if let Err(e) = std::fs::write(&json_path, &text) {
            eprintln!("warning: cannot write {json_path}: {e}");
        }
    }
    println!("{value}");
    if failed {
        std::process::exit(1);
    }
}
