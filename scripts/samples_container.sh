#!/usr/bin/env bash
#
# Generate or verify the sample corpus inside the pinned backend image.
#
# OCCT's mesher makes different discrete triangulation choices on different
# platforms — on a plain rectangular block it splits a quad face along the other
# diagonal — so a corpus generated on one host can never match one generated on
# another, even though the solids are identical in volume, bounding box and
# triangle count. Byte-exact verification is only meaningful against a fixed
# kernel build, so both generation and verification run in the same image the
# delivery containers use.
#
# Set MESH2PARAM_SAMPLES_IMAGE to reuse an image that is already built; the
# image is only built here when it is absent.
set -euo pipefail

action=${1:-check}
image=${MESH2PARAM_SAMPLES_IMAGE:-mesh2param-samples:local}
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
platform=${MESH2PARAM_SAMPLES_PLATFORM:-linux/amd64}

if ! command -v docker >/dev/null 2>&1; then
  echo "samples_container.sh needs docker: the corpus is only reproducible inside the pinned image." >&2
  exit 1
fi

# Rebuild unless the caller names an image it already built from this commit.
# Reusing a stale image would silently verify the corpus against old engine
# code, which is exactly the sort of false pass this check exists to prevent.
# Layer caching makes the repeat build cheap.
if [ -z "${MESH2PARAM_SAMPLES_IMAGE:-}" ]; then
  docker build --platform "$platform" --file "$root/infra/backend.Dockerfile" --tag "$image" "$root" >&2
elif ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "MESH2PARAM_SAMPLES_IMAGE=$image is not present locally." >&2
  exit 1
fi

case "$action" in
  generate)
    container="mesh2param-samples-$$"
    trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
    docker run --name "$container" --platform "$platform" --user 0:0 "$image" \
      python -P -m mesh2param.cli samples generate --output /tmp/generated >/dev/null
    rm -rf "$root/samples/generated"
    docker cp "$container:/tmp/generated" "$root/samples/generated"
    # docker cp restores the container's ownership; make the tree belong to the
    # invoking user again so the checkout stays writable.
    if [ "$(uname)" != "Darwin" ]; then
      docker run --rm --platform "$platform" --user 0:0 -v "$root/samples":/samples "$image" \
        chown -R "$(id -u):$(id -g)" /samples/generated
    fi
    echo "Regenerated $(find "$root/samples/generated" -type f | wc -l | tr -d ' ') sample files from $image"
    ;;
  check)
    # The repository is mounted read-only; the comparison regenerates into the
    # container's own temporary directory.
    diagnostics_args=()
    diagnostics_mount=()
    if [ -n "${MESH2PARAM_SAMPLES_DIAGNOSTICS_DIR:-}" ]; then
      mkdir -p "$MESH2PARAM_SAMPLES_DIAGNOSTICS_DIR"
      diagnostics_root=$(cd "$MESH2PARAM_SAMPLES_DIAGNOSTICS_DIR" && pwd)
      diagnostics_mount=(-v "$diagnostics_root":/diagnostics)
      diagnostics_args=(--generated-output /diagnostics/generated)
    fi
    docker run --rm --platform "$platform" --user 0:0 -v "$root":/src:ro \
      "${diagnostics_mount[@]}" "$image" \
      python -P /src/scripts/check_samples.py --expected /src/samples/generated \
      "${diagnostics_args[@]}"
    ;;
  *)
    echo "usage: samples_container.sh [generate|check]" >&2
    exit 2
    ;;
esac
