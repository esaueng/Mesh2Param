# Agent notes

Project setup, change discipline, and review expectations live in
[`CONTRIBUTING.md`](CONTRIBUTING.md); architecture lives under [`docs/`](docs).
This file carries the per-toolchain command reference.

## Rust core

`crates/mesh2param-core` is a Cargo workspace at the repository root. The
toolchain is pinned in `rust-toolchain.toml`; `Cargo.lock` is committed. The
spikes under `spikes/` are excluded from the workspace and build on their own.

```sh
cargo build -p mesh2param-core                              # build
cargo test --workspace                                      # tests + subset scoreboard
cargo fmt --all --check                                     # formatting
cargo clippy --workspace --all-targets -- -D warnings       # lints

# Corpus scoreboard: writes target/scoreboard.json, compares against
# crates/mesh2param-core/scoreboard-baseline.json.
cargo test -p mesh2param-core --test scoreboard -- --nocapture
MESH2PARAM_SCOREBOARD=full cargo test -p mesh2param-core --test scoreboard -- --nocapture
MESH2PARAM_SCOREBOARD_ONLY=slug/mesh cargo test -p mesh2param-core --test scoreboard -- --nocapture
MESH2PARAM_SCOREBOARD_WRITE_BASELINE=1 cargo test -p mesh2param-core --test scoreboard

# The core must keep building for the browser target.
cargo build -p mesh2param-core --target wasm32-unknown-unknown
```

Re-blessing the baseline and bumping the pinned geometry kernel are documented
in [`crates/mesh2param-core/README.md`](crates/mesh2param-core/README.md).

## WebAssembly package

`crates/mesh2param-wasm` is the `wasm-bindgen` layer over the core;
`packages/core-wasm` is the pnpm package around it. Its `pkg/` is build output
and is gitignored, so nothing that imports the package resolves until it is
built. Needs `wasm-pack` 0.15.0 on `PATH`.

```sh
cargo install --locked wasm-pack --version 0.15.0   # once
pnpm core:wasm                                      # build pkg/ (prints its size)
pnpm build:packages                                 # the JS packages plus pnpm core:wasm
pnpm build:packages:js                              # contracts and ui only, no Rust

pnpm --filter @mesh2param/core-wasm test            # vitest against the built pkg/
pnpm --filter @mesh2param/core-wasm typecheck
pnpm --filter @mesh2param/core-wasm lint
```

Usage, the reported API, and the measured size and speed are in
[`packages/core-wasm/README.md`](packages/core-wasm/README.md).
