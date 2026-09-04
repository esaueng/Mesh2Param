# mesh2param-core

The Phase 1 reconstruction core: **mesh bytes in, STEP bytes out**, on a B-Rep
kernel pinned by revision.

The crate is deliberately pure — no filesystem, no threads, no globals — so the
same code runs in a native test, in a worker process, and in the browser on
`wasm32-unknown-unknown` with nothing stubbed out. Callers own the bytes.

## The ladder

A part is reconstructed at the best tier that holds, falling back region by
region:

| tier | meaning | status |
| --- | --- | --- |
| `Analytic` | every face is a recognised surface (plane, cylinder, cone, sphere, torus) | not implemented |
| `Mixed` | analytic where recognition succeeded, faceted where it declined | not implemented |
| `Faceted` | planar facets throughout | `faceted_step` |

The faceted tier is the floor: it is what every higher tier has to beat, and the
fallback whenever a higher tier declines a region.

### What the faceted tier does, and does not, do

`import_mesh` → validate → `unify_faces` → validate → `write_step`.

`heal_solid` is **not** in the chain. On faceted input it opens or splits closed
shells: 69 of the 111 corpus solids that import as valid come out of healing
invalid (38 with boundary edges, 31 failing Euler). Filed upstream as
esaueng/remus#244. Re-measure with the scoreboard before putting it back.

A solid that is produced but invalid is not an error — it comes back with
`valid: false` and its issues. The scoreboard needs to tell "the kernel refused"
apart from "the kernel produced something questionable".

## Running the scoreboard

The scoreboard walks `samples/real/*/part.json`, runs `faceted_step` on every
mesh, writes `target/scoreboard.json`, prints a table, and compares the outcome
against the committed `scoreboard-baseline.json`.

```bash
# Subset mode: meshes up to 30,000 triangles. ~30 s. This is what CI runs.
cargo test -p mesh2param-core --test scoreboard -- --nocapture

# Everything, including the 150k-triangle exports. Minutes.
MESH2PARAM_SCOREBOARD=full cargo test -p mesh2param-core --test scoreboard -- --nocapture
```

Without `--nocapture` the table is only printed when the test fails;
`target/scoreboard.json` is written either way.

The comparison fails when a mesh that was `valid` in the baseline is not valid
now, when a mesh that did not error now errors, or when a baseline mesh is
missing from the run. Meshes not in the baseline are reported, not failed, so
adding a corpus part does not break the build.

### Re-blessing the baseline

Only after reading the diff and deciding the new numbers are the ones you want:

```bash
MESH2PARAM_SCOREBOARD_WRITE_BASELINE=1 cargo test -p mesh2param-core --test scoreboard
```

The baseline is generated in subset mode and carries no timings, so it does not
change when the machine running it does.

## Bumping the kernel pin

The kernel is a git dependency pinned by revision, never by branch: picking up a
kernel change is a deliberate act with evidence attached, not implicit drift.

1. Record the current scoreboard: `cargo test -p mesh2param-core --test scoreboard -- --nocapture > before.txt`.
2. Edit `Cargo.toml` and replace `rev = "..."` on **all four** kernel
   dependencies with the new revision. They must stay identical — a mismatch
   pulls two copies of the kernel into one build.
3. `cargo update -p remus-io -p remus-math -p remus-operations -p remus-topology`
   (or just `cargo build`, which relocks), then commit `Cargo.lock`.
4. Re-run the scoreboard. Any regression is a reason not to bump; any
   improvement is the justification for bumping.
5. If the numbers moved, re-bless the baseline in the same commit as the pin, so
   the pin and the evidence for it land together.
6. Check `[workspace.lints]` in the root `Cargo.toml` against the kernel's lint
   policy and re-sync if it moved.
