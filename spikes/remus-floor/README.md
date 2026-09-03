# remus-floor

A throwaway measurement spike: how far does the **Remus kernel as it stands
today** get on STL → STEP, with no Mesh2Param logic in the loop?

It runs exactly the chain the WASM bindings expose natively:

```
read_stl_with_limits  ->  import_mesh  ->  validate_solid
                      ->  unify_faces  ->  heal_solid
                      ->  validate_solid  ->  write_step  ->  read_step (round-trip)
```

That is the "floor": planar triangle soup lifted to a B-Rep, same-domain faces
merged, healed, written as AP203. Anything Mesh2Param adds (surface fitting,
primitive recognition, feature reconstruction) has to beat these numbers.

## Exact Remus API used

| step | call |
| --- | --- |
| parse STL | `remus_io::stl::reader::read_stl_with_limits(&bytes, limits)` |
| mesh → B-Rep | `remus_io::stl::import::import_mesh(&mut topo, &mesh, 1e-7)` |
| validate | `remus_operations::validate::validate_solid(&topo, solid)` |
| unify same-domain faces | `remus_operations::heal::unify_faces(&mut topo, solid)` |
| heal | `remus_operations::heal::heal_solid(&mut topo, solid, 1e-7)` |
| write STEP | `remus_io::step::writer::write_step(&topo, &[solid])` |
| read STEP back | `remus_io::step::reader::read_step_with_limits(&text, &mut fresh_topo, limits)` |
| face counts | `remus_topology::explorer::solid_faces(&topo, solid)` |

The `1e-7` tolerance is `crate::helpers::TOL` from `crates/wasm`, i.e. the same
value the browser build passes.

## Build

`cargo` is not on the default PATH on this machine. Either:

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH"
cargo build --release
```

or let `run_corpus.sh` discover a toolchain itself.

This is a **standalone package**, not a member of any workspace (note the empty
`[workspace]` table in `Cargo.toml`, which also stops Cargo from adopting a
parent workspace).

Path dependencies use relative paths that resolve from the spike directory:

```
../../../../../../remus/crates/{io,operations,topology}
```

i.e. `spikes/remus-floor` → worktree root → `.claude/worktrees` → `.claude` →
`Mesh2Param` → `~/claude` → `remus`. Relative paths work because
`~/claude/remus` and this worktree live under a common ancestor; if the spike is
ever moved, swap them for absolute paths. The Remus repo is read-only here — the
build only reads it, and all artifacts land in this spike's own `target/`.

## Binary

```bash
remus-floor --stl <path.stl> --out <dir> [--limits-mb N] [--skip-heal]
```

One mesh per invocation, so per-part peak RSS is measurable from outside with
`/usr/bin/time -l`. Prints exactly one JSON object on stdout. Every stage is
wrapped in `catch_unwind`, so a panic or an `Err` becomes a JSON field rather
than a crash: partial measurements are always emitted.

Keys: `stl`, `mode`, `triangles`, `importMs`, `importError`, `facesImported`,
`validImported`, `unifyMs`, `facesUnified`, `validUnified`, `healMs`,
`facesHealed`, `validFinal`, `validationIssues` (≤10 short strings), `stepMs`,
`stepBytes`, `stepPath`, `reimportMs`, `reimportOk`, `totalMs`, `error`.

Validity is sampled at three points — `validImported` (straight off
`import_mesh`), `validUnified` (after `unify_faces`, before healing), and
`validFinal` — so a regression can be pinned to a stage.

`--skip-heal` omits `heal_solid` entirely; `healMs` and `facesHealed` are then
`null` and `validFinal` equals `validUnified`. `mode` is `heal` or `skip-heal`,
and STEP goes to `<out>/<mode>/<stem>.step` so the two runs never collide.

`reimportOk` is true only when Remus's own STEP reader reads the written file
back to exactly one solid with the same face count as the exported solid.

## Corpus runner

```bash
./run_corpus.sh                 # full chain
MODE=skip-heal ./run_corpus.sh  # same chain minus heal_solid
```

Builds release, walks every `samples/real/*/mesh-*.stl` in the worktree, runs
each under `/usr/bin/time -l`, and appends one JSON line per mesh (plus `slug`,
`mesh`, `peakRssMb`) to `$SCRATCH/remus-floor/results-<mode>.jsonl`. STEP output
goes to `$SCRATCH/remus-floor/<slug>/<mode>/<mesh>.step`.

macOS has no `timeout(1)`, so the per-mesh watchdog is
`perl -e 'alarm shift; exec @ARGV' 120 ...` — `alarm` survives `exec`, and a
killed run is recorded as `"error": "timeout"`.

Env overrides: `MODE` (`heal` | `skip-heal`, default `heal`), `SCRATCH`,
`LIMIT_SEC` (default 120), `CARGO`, `LIMITS_MB`.
