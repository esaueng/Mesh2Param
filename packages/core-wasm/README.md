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
in a worker: a 70k-triangle part occupies the thread for minutes.

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
Native numbers are the corpus scoreboard's, which runs at `opt-level = 2` with
debug assertions on, so they flatter the browser less than a release native
build would.

| mesh | triangles | wasm | native (scoreboard) |
| --- | --- | --- | --- |
| `dovetail-slide-block/mesh-coarse` | 356 | 0.23 s | 0.08 s |
| `hammer-holder/mesh-coarse` | 4 900 | 1.6 s | 0.41 s |
| `hammer-holder/mesh-export` | 70 038 | 493 s | 63 s |

`.wasm` size: **1 822 674 bytes raw, 648 481 gzipped**.

The size/speed trade-off was measured rather than assumed. Building at
`opt-level = "z"` with `wasm-opt -Oz` gives 1 313 565 bytes raw / 506 379
gzipped — 22% smaller compressed — and costs 2.4x on the dovetail block
(0.23 s to 0.57 s) and 1.5x on the hammer holder (1.6 s to 2.4 s). At 633 KiB
gzipped the fast build is nowhere near a size that would justify that, so it is
what ships.

`hammer-holder/mesh-export` is the reason the vitest suite runs the *coarse*
mesh of that part: it reconstructs correctly (mixed tier, valid, 47 593 faces,
a 66 MB STEP file) but spends about 7 of its 8 minutes in verification, whose
distance queries run over the result's own 47k-face tessellation. That is a
core-side cost, not a binding one, and it is what makes a triangle budget on
this path a product decision rather than a formality.
