#!/usr/bin/env bash
# Run the segmentation spike over the eight probe meshes and append one JSON
# line per mesh (with slug, mesh, wall seconds and peak RSS) to
# <scratchpad>/segmentation/results.jsonl. Per-part JSON and PLY land in
# <scratchpad>/segmentation/<slug>/.
#
# Env overrides: SCRATCH (output root), LIMIT_SEC (per-mesh wall clock,
# default 300), CARGO (path to cargo), plus ANGLE_DEG / TOL_FRAC passed to the
# binary.
set -uo pipefail

SPIKE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SPIKE_DIR/../.." && pwd)"

SCRATCH="${SCRATCH:-/private/tmp/claude-501/-Users-userzero-claude-Mesh2Param--claude-worktrees-stl-step-app-overhaul-d172e3/ab589e34-4a2f-4fe4-8dcf-730f02c6e3ad/scratchpad}"
OUT_ROOT="$SCRATCH/segmentation"
RESULTS="$OUT_ROOT/results.jsonl"
LIMIT_SEC="${LIMIT_SEC:-300}"

# One entry per probe mesh: <slug>/<mesh stem>.
PARTS=(
  "hammer-holder/mesh-export"
  "nist-ctc-01/mesh-default"
  "cable-saddle-clamp/mesh-default"
  "thru-hull-hex-nut/mesh-export"
  "windshield-holder-fine/mesh-export"
  "dovetail-slide-block/mesh-coarse"
  "flange-four-bolt/mesh-coarse"
  "motor-mount-nema17/mesh-default"
)

# cargo is not on the default PATH here; fall back to the rustup toolchain.
CARGO="${CARGO:-}"
if [ -z "$CARGO" ]; then
  for tc in "$HOME"/.rustup/toolchains/stable-* "$HOME"/.rustup/toolchains/*; do
    if [ -x "$tc/bin/cargo" ]; then CARGO="$tc/bin/cargo"; PATH="$tc/bin:$PATH"; export PATH; break; fi
  done
fi
[ -x "$CARGO" ] || { echo "cargo not found; set CARGO=..." >&2; exit 1; }

echo "building (release)..." >&2
(cd "$SPIKE_DIR" && "$CARGO" build --release) >&2 || exit 1
BIN="$SPIKE_DIR/target/release/segmentation"

EXTRA=()
[ -n "${ANGLE_DEG:-}" ] && EXTRA+=(--angle-deg "$ANGLE_DEG")
[ -n "${TOL_FRAC:-}" ] && EXTRA+=(--tol-frac "$TOL_FRAC")

mkdir -p "$OUT_ROOT"
: > "$RESULTS"
TMP_OUT="$(mktemp)"; TMP_ERR="$(mktemp)"
trap 'rm -f "$TMP_OUT" "$TMP_ERR"' EXIT

n=0
for entry in "${PARTS[@]}"; do
  slug="${entry%%/*}"
  mesh="${entry##*/}"
  stl="$ROOT/samples/real/$slug/$mesh.stl"
  if [ ! -f "$stl" ]; then
    echo "missing $stl" >&2
    continue
  fi
  out_dir="$OUT_ROOT/$slug"
  mkdir -p "$out_dir"
  n=$((n + 1))
  echo "[$n] $slug/$mesh" >&2

  start=$(python3 -c 'import time; print(time.time())')
  # macOS has no timeout(1): perl's alarm survives exec and kills the child.
  /usr/bin/time -l perl -e 'alarm shift; exec @ARGV' "$LIMIT_SEC" \
    "$BIN" --stl "$stl" --out "$out_dir" "${EXTRA[@]+"${EXTRA[@]}"}" \
    >"$TMP_OUT" 2>"$TMP_ERR"
  rc=$?
  end=$(python3 -c 'import time; print(time.time())')

  rss="$(awk '/maximum resident set size/ {print $1; exit}' "$TMP_ERR")"

  SLUG="$slug" MESH="$mesh" RSS="${rss:-0}" RC="$rc" STL="$stl" \
  START="$start" END="$end" LIMIT="$LIMIT_SEC" \
  python3 -c '
import json, os, sys
raw = sys.stdin.read().strip()
rec = None
for line in raw.splitlines():
    line = line.strip()
    if line.startswith("{"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            rec = None
if rec is None:
    rc = int(os.environ["RC"])
    rec = {"stl": os.environ["STL"],
           "error": "timeout" if rc in (14, 142) else "no output (rc=%d)" % rc}
elif int(os.environ["RC"]) != 0 and not rec.get("error"):
    rec["error"] = "exit %s" % os.environ["RC"]
rec["slug"] = os.environ["SLUG"]
rec["mesh"] = os.environ["MESH"]
rec["wallSeconds"] = round(float(os.environ["END"]) - float(os.environ["START"]), 3)
rec["peakRssMb"] = round(int(os.environ["RSS"] or 0) / (1024 * 1024), 1)
rec.pop("patches", None)
print(json.dumps(rec))
' <"$TMP_OUT" >>"$RESULTS"
done

echo "wrote $n records to $RESULTS" >&2
