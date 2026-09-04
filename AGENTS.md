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
