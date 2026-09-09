# Working agreements

Complete the requested work. Infer scope from context, make reasonable
implementation choices, and continue until finished or genuinely blocked.
Keep investigation-only requests read-only.

An explicit request or prior approval authorizes that action. Do not ask
again. Ask only when consequential ambiguity remains or an additional action
falls outside the authorized scope. Complete independent work while waiting.

Follow repository conventions. Keep changes focused. Preserve units,
tolerances, defaults, formats, and public contracts unless changes are
required. Label approximations and flag breaking changes or new dependencies.

Run required checks and tests proportional to the change. Add regression
coverage for bug fixes. Do not weaken assertions or bypass protections.
Attempt routine recovery from missing tools or Git refs before reporting a
blocker. Distinguish local validation from production verification.

Keep secrets, private instructions, and identifying information out of shared
artifacts. Inspect staged content and metadata before committing. Use the
approved repository Git identity.

## Delivery

- Use a branch and a ready-for-review pull request for repository changes.
- A merge request authorizes the identified pull request’s merge and its
  existing automatic deployment. Mention that consequence and proceed
  without another confirmation.
- Before merging, verify the current head, mergeability, reviews, and required
  checks. Wait for pending checks. Existing approval remains valid for the
  authorized change.
- Bypassing CI requires explicit authorization for the specific pull request.
  Disclose affected checks and risks; preserve review requirements.
- Standalone production deployments and manual migrations require
  authorization. An explicit request to perform them is sufficient.
- Resolve the target repository, environment, and account from configuration
  and context. Ask only if the target remains ambiguous.

Report the outcome briefly, followed by verification, actual blockers, and
relevant links. Never claim an unverified result passed.

---

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
