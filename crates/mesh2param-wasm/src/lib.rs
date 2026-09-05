//! WebAssembly bindings for [`mesh2param_core`].
//!
//! Three synchronous calls — [`version`], [`analyze`], [`reconstruct`] — over
//! the reconstruction ladder. Synchronous on purpose: the whole point of a
//! pure core is that the host decides where it runs, and the web app runs it
//! in a worker where blocking is the correct behaviour.
//!
//! # What crosses the boundary
//!
//! Bytes in, a plain JavaScript object out. Large payloads (the STEP file and
//! the display mesh) are `Uint8Array`, never arrays of numbers: serialising a
//! megabyte of STEP through `serde` one JS number at a time costs more than
//! the reconstruction did.
//!
//! # Errors
//!
//! Every failure is a thrown `Error` carrying [`mesh2param_core::CoreError`]'s
//! own text. A triangle-budget refusal additionally sets `name` to
//! `"BudgetError"` and `code` to `"budget"`, because it is the one failure a
//! caller can act on — offer a coarser mesh — rather than report.

mod glb;

use js_sys::{Function, Reflect, Uint8Array};
use mesh2param_core::{
    Bbox, CoreError, MeshData, MeshFormat, Progress, ReconstructOptions, Stage, Tier, load_mesh,
    reconstruct_with_progress,
};
use serde::{Deserialize, Serialize};
use wasm_bindgen::prelude::*;

/// Install the panic hook once, so a kernel panic reaches the JS console as a
/// stack trace instead of an `unreachable` trap.
///
/// Called at the top of every entry point rather than from a `start` function:
/// `wasm-bindgen`'s start runs before the host has finished wiring the module
/// up in some bundlers, and this is idempotent and free.
fn install_hook() {
    console_error_panic_hook::set_once();
}

/// This binding's version, and the kernel revision it was built against.
///
/// Formatted `"<crate version> (remus <rev>)"`. The revision is read out of the
/// committed `Cargo.lock` at build time by `build.rs`.
#[must_use]
#[wasm_bindgen]
pub fn version() -> String {
    format!(
        "{} (remus {})",
        env!("CARGO_PKG_VERSION"),
        env!("MESH2PARAM_KERNEL_REV")
    )
}

/// Mesh statistics, without reconstructing anything.
///
/// # Errors
///
/// Throws when `format` is not a container the core reads, or when the bytes
/// are not a well-formed mesh.
#[wasm_bindgen]
pub fn analyze(bytes: &[u8], format: &str) -> Result<JsValue, JsValue> {
    install_hook();
    let mesh = load(bytes, format)?;
    let welded = mesh.welded().map_err(throw)?;

    let (boundary_edges, over_used_edges) = edge_counts(&welded.triangles);
    let report = Analysis {
        triangles: mesh.triangles,
        vertices: welded.positions.len(),
        bbox: BboxJson::of(mesh.bbox),
        watertight: boundary_edges == 0 && over_used_edges == 0,
        edge_manifold: over_used_edges == 0,
        non_manifold_edges: welded.non_manifold_edges,
        dropped_triangles: welded.dropped_triangles,
    };
    to_js(&report)
}

/// Run the whole ladder: mesh bytes in, a STEP file and a display mesh out.
///
/// `options` is an object of overrides on the core's defaults; `undefined`,
/// `null` and `{}` all mean "the defaults". `on_progress` is called as
/// `(stage, fraction)` at stage boundaries and at a coarse per-pass
/// granularity inside segmentation and construction; the run is finished when
/// `"step"` reaches `1`.
///
/// # Errors
///
/// Throws when the format is unknown, the bytes are not a mesh, an option is
/// not a number the core accepts, or the mesh is over the triangle budget —
/// the last of these as a `BudgetError`.
#[wasm_bindgen]
pub fn reconstruct(
    bytes: &[u8],
    format: &str,
    options: JsValue,
    on_progress: Option<Function>,
) -> Result<JsValue, JsValue> {
    install_hook();

    let overrides: Overrides = if options.is_undefined() || options.is_null() {
        Overrides::default()
    } else {
        serde_wasm_bindgen::from_value(options)
            .map_err(|e| error(&format!("invalid options: {e}"), None))?
    };
    let core_options = overrides.apply(ReconstructOptions::default());

    let mut timer = StageTimer::new();
    timer.enter(Stage::Parse);
    let mesh = load(bytes, format)?;

    // Scoped so the sink's borrow of the timer ends before it is read back.
    let result = {
        let mut sink = |stage: Stage, fraction: f32| {
            timer.enter(stage);
            if let Some(callback) = on_progress.as_ref() {
                // A throwing progress callback is the caller's problem, not a
                // reason to abandon a reconstruction that is already running.
                let _ = callback.call2(
                    &JsValue::NULL,
                    &JsValue::from_str(stage.as_str()),
                    &JsValue::from_f64(f64::from(fraction)),
                );
            }
        };
        reconstruct_with_progress(&mesh, &core_options, &mut Progress::new(&mut sink))
    }
    .map_err(throw)?;
    let timings = timer.finish();

    let build = &result.build;
    let report = Reconstruction {
        tier: build.tier,
        valid: build.valid,
        issues: build.issues.clone(),
        fallback_reason: build.fallback_reason.clone(),
        faces_analytic: build.faces_analytic,
        faces_triangle: build.faces_triangle,
        faces_final: build.faces_final,
        deviation: build.deviation.map(|d| DeviationJson {
            p95: d.p95,
            max: d.max,
            samples: d.samples,
        }),
        volume: build.volume,
        source_volume: build.source_volume,
        step_bytes: build.step_bytes,
        round_trip_ok: build.round_trip_ok,
        timings,
        inventory: result
            .inventory
            .map_or_else(InventoryJson::default, |i| InventoryJson {
                plane: i.plane,
                cylinder: i.cylinder,
                cone: i.cone,
                torus: i.torus,
                sphere: i.sphere,
                unknown: i.unknown,
            }),
        unknown_area_fraction: result.unknown_area_fraction,
        patches: result.patches,
        edges: result.edges,
    };

    let out = to_js(&report)?;
    set_bytes(&out, "step", &build.step)?;
    let glb = glb::write(&build.mesh.positions, &build.mesh.indices);
    set_bytes(&out, "glb", &glb)?;
    Ok(out)
}

/// Parse `bytes` in the named container.
fn load(bytes: &[u8], format: &str) -> Result<MeshData, JsValue> {
    let format = match format.to_ascii_lowercase().as_str() {
        "stl" => MeshFormat::Stl,
        "3mf" | "threemf" => MeshFormat::ThreeMf,
        "obj" => MeshFormat::Obj,
        "ply" => MeshFormat::Ply,
        other => {
            return Err(error(
                &format!("unsupported mesh format: {other}"),
                Some("format"),
            ));
        }
    };
    load_mesh(bytes, format).map_err(throw)
}

/// Boundary edges (one owning triangle) and over-used edges (more than two).
fn edge_counts(triangles: &[[u32; 3]]) -> (usize, usize) {
    let mut counts: std::collections::HashMap<(u32, u32), u32> = std::collections::HashMap::new();
    for tri in triangles {
        for i in 0..3 {
            let (a, b) = (tri[i], tri[(i + 1) % 3]);
            *counts.entry((a.min(b), a.max(b))).or_default() += 1;
        }
    }
    let boundary = counts.values().filter(|&&n| n < 2).count();
    let over = counts.values().filter(|&&n| n > 2).count();
    (boundary, over)
}

/// Attach a `Uint8Array` to the result object.
fn set_bytes(target: &JsValue, key: &str, bytes: &[u8]) -> Result<(), JsValue> {
    let view = Uint8Array::new_with_length(
        u32::try_from(bytes.len())
            .map_err(|_| error("result is larger than a Uint8Array can hold", None))?,
    );
    view.copy_from(bytes);
    Reflect::set(target, &JsValue::from_str(key), &view)?;
    Ok(())
}

/// Serialise a report as a plain JavaScript object.
fn to_js<T: Serialize>(value: &T) -> Result<JsValue, JsValue> {
    let serializer = serde_wasm_bindgen::Serializer::new().serialize_maps_as_objects(true);
    value
        .serialize(&serializer)
        .map_err(|e| error(&format!("could not serialise the result: {e}"), None))
}

/// A [`CoreError`] as the JS `Error` the caller sees.
fn throw(error_value: CoreError) -> JsValue {
    let code = match error_value {
        CoreError::Budget { .. } => Some("budget"),
        CoreError::Parse(_) => Some("parse"),
        CoreError::Unsupported(_) => Some("format"),
        _ => None,
    };
    error(&error_value.to_string(), code)
}

/// Build a JS `Error` with a message and an optional machine-readable `code`.
///
/// A budget refusal also takes `name = "BudgetError"`: `name` is what
/// `instanceof`-style dispatch in JS reads, and callers should not have to
/// match on the message text.
fn error(message: &str, code: Option<&str>) -> JsValue {
    let err = js_sys::Error::new(message);
    if let Some(code) = code {
        drop(Reflect::set(
            &err,
            &JsValue::from_str("code"),
            &JsValue::from_str(code),
        ));
        if code == "budget" {
            err.set_name("BudgetError");
        }
    }
    JsValue::from(err)
}

/// Per-stage wall clock, taken on this side of the boundary.
///
/// The core has no clock on `wasm32-unknown-unknown` — `Instant::now` traps
/// there — so its own `ms_*` fields read zero in the browser. The progress
/// reports are stage transitions, which is exactly what is needed to time the
/// stages from outside.
struct StageTimer {
    current: Option<Stage>,
    since: f64,
    parse: f64,
    segment: f64,
    topology: f64,
    build: f64,
    verify: f64,
    step: f64,
}

impl StageTimer {
    fn new() -> Self {
        Self {
            current: None,
            since: now(),
            parse: 0.0,
            segment: 0.0,
            topology: 0.0,
            build: 0.0,
            verify: 0.0,
            step: 0.0,
        }
    }

    /// Charge the time since the last transition to the stage that was running,
    /// and start the clock on `stage`.
    fn enter(&mut self, stage: Stage) {
        if self.current == Some(stage) {
            return;
        }
        let at = now();
        self.charge(at - self.since);
        self.current = Some(stage);
        self.since = at;
    }

    fn charge(&mut self, elapsed: f64) {
        // Welding is the first half of recognition from a caller's point of
        // view, and nothing downstream can tell them apart, so it is charged
        // there rather than reported as a stage of its own.
        match self.current {
            Some(Stage::Parse) => self.parse += elapsed,
            Some(Stage::Weld | Stage::Segment) => self.segment += elapsed,
            Some(Stage::Topology) => self.topology += elapsed,
            Some(Stage::Build) => self.build += elapsed,
            Some(Stage::Verify) => self.verify += elapsed,
            Some(Stage::Step) => self.step += elapsed,
            None => {}
        }
    }

    fn finish(mut self) -> Timings {
        let at = now();
        self.charge(at - self.since);
        Timings {
            parse: self.parse,
            segment: self.segment,
            topology: self.topology,
            build: self.build,
            verify: self.verify,
            step: self.step,
        }
    }
}

/// Milliseconds since the epoch, from the host.
fn now() -> f64 {
    js_sys::Date::now()
}

/// Overrides on [`ReconstructOptions`], all optional.
///
/// A deliberately small surface: the knobs a caller has a reason to move.
/// Everything else stays at the core's default, which is what the corpus
/// scoreboard is measured at.
#[derive(Debug, Default, Deserialize)]
#[serde(rename_all = "camelCase", default, deny_unknown_fields)]
struct Overrides {
    /// Refuse meshes above this triangle count. Defaults to 200 000.
    triangle_budget: Option<usize>,
    /// Absolute tolerance for construction. `None` follows segmentation.
    tolerance: Option<f64>,
    /// Chord deflection for the verification tessellation, which is also the
    /// display mesh.
    deflection: Option<f64>,
    /// Measure the result against the source mesh. Off makes `deviation` null
    /// and leaves the display mesh empty.
    verify: Option<bool>,
    /// Merge same-surface adjacent faces before validating.
    unify: Option<bool>,
    /// Cap on demote-and-rebuild rounds before the faceted fallback.
    max_rounds: Option<usize>,
    /// Largest volume error a result may have above the faceted tier.
    max_volume_error: Option<f64>,
    /// Largest deviation p95, as a fraction of the bounding-box diagonal.
    max_deviation_fraction: Option<f64>,
    /// Dihedral threshold for the initial over-segmentation, in degrees.
    angle_deg: Option<f64>,
}

impl Overrides {
    fn apply(self, mut options: ReconstructOptions) -> ReconstructOptions {
        if let Some(budget) = self.triangle_budget {
            options.build.triangle_budget = budget;
            options.faceted.triangle_budget = budget;
        }
        if let Some(tolerance) = self.tolerance {
            options.build.tolerance = Some(tolerance);
        }
        if let Some(deflection) = self.deflection {
            options.build.deflection = Some(deflection);
        }
        if let Some(verify) = self.verify {
            options.build.verify = verify;
        }
        if let Some(unify) = self.unify {
            options.build.unify = unify;
        }
        if let Some(rounds) = self.max_rounds {
            options.build.max_rounds = rounds;
        }
        if let Some(error) = self.max_volume_error {
            options.build.max_volume_error = error;
        }
        if let Some(fraction) = self.max_deviation_fraction {
            options.build.max_deviation_fraction = fraction;
        }
        if let Some(angle) = self.angle_deg {
            options.segment.angle_deg = angle;
        }
        options
    }
}

/// What [`analyze`] reports.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Analysis {
    triangles: usize,
    vertices: usize,
    bbox: BboxJson,
    watertight: bool,
    edge_manifold: bool,
    non_manifold_edges: usize,
    dropped_triangles: usize,
}

/// An axis-aligned box as `{min, max}`.
#[derive(Debug, Serialize)]
struct BboxJson {
    min: [f64; 3],
    max: [f64; 3],
}

impl BboxJson {
    const fn of(bbox: Bbox) -> Self {
        Self {
            min: bbox.min,
            max: bbox.max,
        }
    }
}

/// What [`reconstruct`] reports, before `step` and `glb` are attached.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Reconstruction {
    tier: Tier,
    valid: bool,
    issues: Vec<String>,
    fallback_reason: Option<String>,
    faces_analytic: usize,
    faces_triangle: usize,
    faces_final: usize,
    deviation: Option<DeviationJson>,
    volume: f64,
    source_volume: f64,
    step_bytes: usize,
    round_trip_ok: bool,
    timings: Timings,
    inventory: InventoryJson,
    unknown_area_fraction: f64,
    patches: Option<usize>,
    edges: Option<usize>,
}

/// Distance between the result and the source mesh.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DeviationJson {
    p95: f64,
    max: f64,
    samples: usize,
}

/// Recognised surfaces, by type.
#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct InventoryJson {
    plane: u32,
    cylinder: u32,
    cone: u32,
    torus: u32,
    sphere: u32,
    unknown: u32,
}

/// Per-stage wall clock, milliseconds.
#[derive(Debug, Serialize)]
struct Timings {
    #[serde(rename = "parseMs")]
    parse: f64,
    #[serde(rename = "segmentMs")]
    segment: f64,
    #[serde(rename = "topologyMs")]
    topology: f64,
    #[serde(rename = "buildMs")]
    build: f64,
    #[serde(rename = "verifyMs")]
    verify: f64,
    #[serde(rename = "stepMs")]
    step: f64,
}
