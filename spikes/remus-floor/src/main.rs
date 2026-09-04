//! Measures the "Remus floor": STL -> B-Rep -> unify -> heal -> STEP, one mesh
//! per process so peak RSS is attributable to a single part.
//!
//! Mirrors the native call chain used by the WASM bindings
//! (`crates/wasm/src/bindings/io.rs`, `.../heal.rs`).

use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::PathBuf;
use std::time::Instant;

use remus_io::ImportLimits;
use remus_operations::validate::{Severity, ValidationReport};
use remus_topology::Topology;
use remus_topology::solid::SolidId;

/// Same tolerance the WASM bindings pass to `import_mesh` (`helpers::TOL`).
const TOL: f64 = 1e-7;

struct Args {
    stl: PathBuf,
    out: PathBuf,
    limits_mb: Option<usize>,
    skip_heal: bool,
}

impl Args {
    /// Sub-directory (and reported mode) so the two runs cannot overwrite each other.
    fn mode(&self) -> &'static str {
        if self.skip_heal { "skip-heal" } else { "heal" }
    }
}

fn parse_args() -> Result<Args, String> {
    let (mut stl, mut out, mut limits_mb) = (None, None, None);
    let mut skip_heal = false;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--stl" => stl = it.next().map(PathBuf::from),
            "--out" => out = it.next().map(PathBuf::from),
            "--skip-heal" => skip_heal = true,
            "--limits-mb" => {
                limits_mb = match it.next().map(|v| v.parse::<usize>()) {
                    Some(Ok(n)) => Some(n),
                    _ => return Err("--limits-mb needs a number".into()),
                };
            }
            other => return Err(format!("unknown argument {other}")),
        }
    }
    Ok(Args {
        stl: stl.ok_or("missing --stl")?,
        out: out.ok_or("missing --out")?,
        limits_mb,
        skip_heal,
    })
}

/// Run one fallible stage, turning panics into errors so the JSON is always emitted.
fn stage<T>(f: impl FnOnce() -> Result<T, String>) -> Result<T, String> {
    match catch_unwind(AssertUnwindSafe(f)) {
        Ok(r) => r,
        Err(p) => {
            let msg = p
                .downcast_ref::<&str>()
                .map(|s| (*s).to_string())
                .or_else(|| p.downcast_ref::<String>().cloned())
                .unwrap_or_else(|| "unknown".into());
            Err(format!("panic: {msg}"))
        }
    }
}

fn short(s: &str) -> String {
    let one = s.replace('\n', " ");
    if one.chars().count() > 160 {
        one.chars().take(157).collect::<String>() + "..."
    } else {
        one
    }
}

fn issues_of(report: &ValidationReport) -> Vec<String> {
    report
        .issues
        .iter()
        .take(10)
        .map(|i| {
            let sev = match i.severity {
                Severity::Error => "error",
                Severity::Warning => "warn",
            };
            short(&format!("{sev}: {}", i.description))
        })
        .collect()
}

fn face_count(topo: &Topology, solid: SolidId) -> u64 {
    remus_topology::explorer::solid_faces(topo, solid).map_or(0, |f| f.len() as u64)
}

fn ms(start: Instant) -> f64 {
    start.elapsed().as_secs_f64() * 1000.0
}

#[allow(clippy::too_many_lines)]
fn main() {
    let mut j = serde_json::Map::new();
    let mut set = |k: &str, v: serde_json::Value| {
        j.insert(k.to_string(), v);
    };
    // Defaults so the shape of the object never varies.
    for k in ["importError", "error", "stepPath"] {
        set(k, serde_json::Value::Null);
    }
    for k in [
        "triangles",
        "facesImported",
        "facesUnified",
        "facesHealed",
        "stepBytes",
    ] {
        set(k, 0.into());
    }
    for k in ["importMs", "unifyMs", "healMs", "stepMs", "reimportMs"] {
        set(k, 0.into());
    }
    for k in ["validImported", "validUnified", "validFinal", "reimportOk"] {
        set(k, false.into());
    }
    set("validationIssues", serde_json::Value::Array(vec![]));

    let t_all = Instant::now();
    let args = match parse_args() {
        Ok(a) => a,
        Err(e) => {
            set("stl", serde_json::Value::Null);
            set("mode", "heal".into());
            set("error", e.into());
            set("totalMs", ms(t_all).into());
            println!("{}", serde_json::Value::Object(j));
            return;
        }
    };
    set("stl", args.stl.to_string_lossy().to_string().into());
    set("mode", args.mode().into());
    if args.skip_heal {
        set("healMs", serde_json::Value::Null);
        set("facesHealed", serde_json::Value::Null);
    }

    let mut limits = ImportLimits::default();
    if let Some(mb) = args.limits_mb {
        limits.max_input_bytes = mb * 1024 * 1024;
    }

    let mut topo = Topology::new();
    let mut fatal: Option<String> = None;

    // ── import: read STL + build planar B-Rep faces ────────────────
    let t = Instant::now();
    let imported = stage(|| {
        let bytes = std::fs::read(&args.stl).map_err(|e| format!("read {}: {e}", args.stl.display()))?;
        let mesh = remus_io::stl::reader::read_stl_with_limits(&bytes, limits)
            .map_err(|e| format!("read_stl: {e}"))?;
        let tris = mesh.indices.len() / 3;
        let solid = remus_io::stl::import::import_mesh(&mut topo, &mesh, TOL)
            .map_err(|e| format!("import_mesh: {e}"))?;
        Ok((tris, solid))
    });
    set("importMs", ms(t).into());

    let solid = match imported {
        Ok((tris, solid)) => {
            set("triangles", tris.into());
            set("facesImported", face_count(&topo, solid).into());
            Some(solid)
        }
        Err(e) => {
            set("importError", short(&e).into());
            fatal = Some(short(&e));
            None
        }
    };

    if let Some(solid) = solid {
        // ── validate (as imported) ─────────────────────────────────
        if let Ok(rep) = stage(|| {
            remus_operations::validate::validate_solid(&topo, solid).map_err(|e| e.to_string())
        }) {
            set("validImported", rep.is_valid().into());
        }

        // ── unify same-domain faces ────────────────────────────────
        let t = Instant::now();
        let unified = stage(|| {
            remus_operations::heal::unify_faces(&mut topo, solid).map_err(|e| e.to_string())
        });
        set("unifyMs", ms(t).into());
        if let Err(e) = &unified {
            fatal.get_or_insert(short(&format!("unify: {e}")));
        }
        set("facesUnified", face_count(&topo, solid).into());

        // ── validate (after unify, before heal) ────────────────────
        if let Ok(rep) = stage(|| {
            remus_operations::validate::validate_solid(&topo, solid).map_err(|e| e.to_string())
        }) {
            set("validUnified", rep.is_valid().into());
        }

        // ── heal (skipped under --skip-heal) ───────────────────────
        if !args.skip_heal {
            let t = Instant::now();
            let healed = stage(|| {
                remus_operations::heal::heal_solid(&mut topo, solid, TOL).map_err(|e| e.to_string())
            });
            set("healMs", ms(t).into());
            if let Err(e) = &healed {
                fatal.get_or_insert(short(&format!("heal: {e}")));
            }
            set("facesHealed", face_count(&topo, solid).into());
        }

        // ── validate (final) ───────────────────────────────────────
        let final_faces = face_count(&topo, solid);
        if let Ok(rep) = stage(|| {
            remus_operations::validate::validate_solid(&topo, solid).map_err(|e| e.to_string())
        }) {
            set("validFinal", rep.is_valid().into());
            set("validationIssues", issues_of(&rep).into());
        }

        // ── write STEP ─────────────────────────────────────────────
        let t = Instant::now();
        let written = stage(|| {
            let text = remus_io::step::writer::write_step(&topo, &[solid])
                .map_err(|e| format!("write_step: {e}"))?;
            // Per-mode sub-directory so the heal and skip-heal runs coexist.
            let dir = args.out.join(args.mode());
            std::fs::create_dir_all(&dir).map_err(|e| format!("mkdir out: {e}"))?;
            let stem = args
                .stl
                .file_stem()
                .map_or_else(|| "part".to_string(), |s| s.to_string_lossy().to_string());
            let path = dir.join(format!("{stem}.step"));
            std::fs::write(&path, text.as_bytes()).map_err(|e| format!("write step: {e}"))?;
            Ok((text.len(), path, text))
        });
        set("stepMs", ms(t).into());

        match written {
            Ok((bytes, path, text)) => {
                set("stepBytes", bytes.into());
                set("stepPath", path.to_string_lossy().to_string().into());

                // ── re-import with Remus's own STEP reader ─────────
                let t = Instant::now();
                let back = stage(|| {
                    let mut fresh = Topology::new();
                    let solids = remus_io::step::reader::read_step_with_limits(&text, &mut fresh, limits)
                        .map_err(|e| format!("read_step: {e}"))?;
                    if solids.len() != 1 {
                        return Err(format!("read_step returned {} solids", solids.len()));
                    }
                    Ok(face_count(&fresh, solids[0]))
                });
                set("reimportMs", ms(t).into());
                match back {
                    Ok(n) => set("reimportOk", (n == final_faces).into()),
                    Err(e) => {
                        fatal.get_or_insert(short(&format!("reimport: {e}")));
                    }
                }
            }
            Err(e) => {
                fatal.get_or_insert(short(&e));
            }
        }
    }

    set("totalMs", ms(t_all).into());
    if let Some(e) = fatal {
        set("error", e.into());
    }
    println!("{}", serde_json::Value::Object(j));
}
