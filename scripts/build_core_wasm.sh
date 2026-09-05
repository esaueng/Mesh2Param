#!/usr/bin/env bash
# Build the reconstruction core as WebAssembly into packages/core-wasm/pkg.
#
# wasm-pack drives cargo and wasm-bindgen together, so the CLI's schema version
# has to match the `wasm-bindgen` pinned in crates/mesh2param-wasm/Cargo.toml —
# a mismatch fails the build rather than producing something subtly wrong.
# `pkg/` is build output and is gitignored: nothing resolves @mesh2param/core-wasm
# on a clean checkout until this has run, which is what `pnpm build:packages`
# is for.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
crate="$root/crates/mesh2param-wasm"
out="$root/packages/core-wasm/pkg"

if ! command -v wasm-pack >/dev/null 2>&1; then
  echo "wasm-pack is not on PATH; install it with 'cargo install --locked wasm-pack --version 0.15.0'" >&2
  exit 1
fi

rm -rf "$out"
wasm-pack build "$crate" \
  --target web \
  --release \
  --out-dir "$out" \
  --out-name mesh2param_wasm \
  --no-pack

wasm="$out/mesh2param_wasm_bg.wasm"
raw=$(wc -c <"$wasm" | tr -d ' ')
gz=$(gzip -9 -c "$wasm" | wc -c | tr -d ' ')
printf 'core-wasm: %s bytes raw, %s bytes gzipped\n' "$raw" "$gz"
