#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export PATH="${CARGO_HOME:-$HOME/.cargo}/bin:$PATH"

if ! command -v rustup >/dev/null 2>&1; then
  installer=$(mktemp)
  trap 'rm -f "$installer"' EXIT
  curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
    https://sh.rustup.rs --output "$installer"
  sh "$installer" -y --profile minimal --default-toolchain none --no-modify-path
fi

toolchain=$(sed -n 's/^channel = "\([^"]*\)"$/\1/p' rust-toolchain.toml)
if [ -z "$toolchain" ]; then
  echo "Cannot read the Rust toolchain pin from rust-toolchain.toml" >&2
  exit 1
fi
rustup toolchain install "$toolchain" --profile minimal --target wasm32-unknown-unknown

if [ "$(wasm-pack --version 2>/dev/null || true)" != "wasm-pack 0.15.0" ]; then
  cargo install --locked wasm-pack --version 0.15.0 --force
fi
wasm-pack --version
