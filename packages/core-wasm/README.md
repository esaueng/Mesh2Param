# `@mesh2param/core-wasm`

The Rust reconstruction core (`crates/mesh2param-core`) compiled to
WebAssembly, with a hand-written TypeScript wrapper over the generated
bindings. Mesh bytes in, a STEP file and a display mesh out, with no server.

## Building

```sh
pnpm core:wasm                      # or: bash scripts/build_core_wasm.sh
pnpm build:packages                 # builds this along with contracts and ui
```

`pkg/` is wasm-pack output and is gitignored: nothing that imports this package
resolves on a clean checkout until the build has run. The build needs the
pinned Rust toolchain and `wasm-pack` 0.15.0 on `PATH`
(`cargo install --locked wasm-pack --version 0.15.0`); the `wasm-bindgen`
version in `crates/mesh2param-wasm/Cargo.toml` is pinned exactly and has to
match the CLI wasm-pack drives.

```sh
pnpm --filter @mesh2param/core-wasm test        # vitest, loads pkg/ from disk
pnpm --filter @mesh2param/core-wasm typecheck
pnpm --filter @mesh2param/core-wasm lint        # currently an alias of typecheck
```

## Using it

```ts
import { init, analyze, reconstruct, version } from "@mesh2param/core-wasm";

await init();                                   // or init(bytes) in Node
const stats = analyze(bytes);                   // triangles, bbox, watertight, …
const result = reconstruct(bytes, "stl", { triangleBudget: 200_000 }, (stage, fraction) => {
  postMessage({ progress: true, stage, fraction });
});
result.step;                                    // Uint8Array, AP203 STEP
result.glb;                                     // Uint8Array, binary glTF
```

Every call is synchronous once `init` has resolved, which is why this belongs
in a worker: a 70k-triangle part occupies the thread for the best part of a
minute.

`init` is idempotent and returns the first call's promise, so several callers
may await it without racing. In Node, pass the bytes
(`init(await readFile(wasmPath))`); in a bundler that rewrites
`import.meta.url`, call it with no argument.

### Errors

Every failure throws an `Error` carrying the core's own message. A mesh over
the triangle budget throws with `name === "BudgetError"` and
`code === "budget"` — the one failure a caller can act on (offer a coarser
mesh) rather than only report. A kernel panic surfaces as a JS error with a
stack trace, via `console_error_panic_hook`.

### Progress

`stage` is one of `parse`, `weld`, `segment`, `topology`, `build`, `verify`,
`step`. `fraction` runs 0 to 1 **within each stage**, not across the run;
stages are not equally sized, so a caller wanting one overall number has to
weight them itself. The run is finished exactly when `step` reaches `1`.

`timings` is measured on the JavaScript side rather than in the core:
`wasm32-unknown-unknown` has no clock, `Instant::now` traps there, and the
core's own `ms_*` fields consequently read zero in a browser.

## Measured

Apple M-series, Node 22, release build (`opt-level = 3`, LTO, `wasm-opt -O`).
Both columns are whole-reconstruct wall clock for the same release settings, so
the ratio between them is the cost of the browser target and nothing else.

| mesh | triangles | wasm | native |
| --- | --- | --- | --- |
| `dovetail-slide-block/mesh-coarse` | 356 | 0.15 s | 0.03 s |
| `hammer-holder/mesh-coarse` | 4 900 | 0.82 s | 0.27 s |
| `hammer-holder/mesh-export` | 70 038 | 53 s | 25 s |

`.wasm` size: **1 831 606 bytes raw, 651 015 gzipped**.

The size/speed trade-off was measured rather than assumed. Building at
`opt-level = "z"` with `wasm-opt -Oz` gives 1 313 565 bytes raw / 506 379
gzipped — 22% smaller compressed — and costs 2.4x on the dovetail block
(0.23 s to 0.57 s) and 1.5x on the hammer holder (1.6 s to 2.4 s), both measured
against the slower pre-BVH core; the ratios are the point, not the absolute
numbers. At 636 KiB
gzipped the fast build is nowhere near a size that would justify that, so it is
what ships.

`hammer-holder/mesh-export` used to be the reason the vitest suite ran only the
*coarse* mesh of that part: it reconstructed correctly (mixed tier, valid, a
66 MB STEP file) but spent about 7 of its 8 minutes in verification, whose
distance queries run over the result's own 47k-face tessellation. Replacing that
query's uniform grid with a BVH took the whole run from 493 s to 53 s here, and
its verify stage from 16.6 s to 0.65 s in a native release build, so the export
now runs in the suite too, under a 90 s bound. See the crate README's
verification section for why a grid cannot serve this input.

What is left is not verification. Of the export's 25 s native, 21 s is
`remus_operations::heal::unify_faces` — 9.6 s per build round, and this mesh
takes the demote-and-rebuild retry, so it pays for two — against 0.65 s of
verify, 0.06 s of assembly and 1.2 s of STEP write plus read-back. Speeding this
path up further is a kernel-side question, and a triangle budget on it remains a
product decision rather than a formality.
