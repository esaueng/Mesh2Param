#!/usr/bin/env bash
# Run the remus-floor probe over every samples/real/*/mesh-*.stl, one process
# per mesh, and append a JSON line per mesh to <scratchpad>/remus-floor/results.jsonl.
#
# Env overrides: SCRATCH (output root), LIMIT_SEC (per-mesh wall clock, default 120),
# CARGO (path to cargo), LIMITS_MB (passed through as --limits-mb).
set -uo pipefail

SPIKE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SPIKE_DIR/../.." && pwd)"

SCRATCH="${SCRATCH:-/private/tmp/claude-501/-Users-userzero-claude-Mesh2Param--claude-worktrees-stl-step-app-overhaul-d172e3/ab589e34-4a2f-4fe4-8dcf-730f02c6e3ad/scratchpad}"
OUT_ROOT="$SCRATCH/remus-floor"
LIMIT_SEC="${LIMIT_SEC:-120}"

MODE="${MODE:-heal}"
case "$MODE" in
  heal) MODE_FLAG=() ;;
  skip-heal) MODE_FLAG=(--skip-heal) ;;
  *) echo "MODE must be heal or skip-heal (got '$MODE')" >&2; exit 1 ;;
esac
RESULTS="$OUT_ROOT/results-$MODE.jsonl"

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
BIN="$SPIKE_DIR/target/release/remus-floor"

mkdir -p "$OUT_ROOT"
: > "$RESULTS"
TMP_OUT="$(mktemp)"; TMP_ERR="$(mktemp)"
trap 'rm -f "$TMP_OUT" "$TMP_ERR"' EXIT

n=0
for stl in "$ROOT"/samples/real/*/mesh-*.stl; do
  [ -f "$stl" ] || continue
  slug="$(basename "$(dirname "$stl")")"
  mesh="$(basename "$stl" .stl)"
  out_dir="$OUT_ROOT/$slug"
  mkdir -p "$out_dir"
  n=$((n + 1))
  echo "[$n] $slug/$mesh" >&2

  extra=("${MODE_FLAG[@]+"${MODE_FLAG[@]}"}")
  [ -n "${LIMITS_MB:-}" ] && extra+=(--limits-mb "$LIMITS_MB")

  # macOS has no timeout(1): perl's alarm survives exec and kills the child.
  /usr/bin/time -l perl -e 'alarm shift; exec @ARGV' "$LIMIT_SEC" \
    "$BIN" --stl "$stl" --out "$out_dir" "${extra[@]+"${extra[@]}"}" \
    >"$TMP_OUT" 2>"$TMP_ERR"
  rc=$?

  rss="$(awk '/maximum resident set size/ {print $1; exit}' "$TMP_ERR")"

  SLUG="$slug" MESH="$mesh" RSS="${rss:-0}" RC="$rc" STL="$stl" LIMIT="$LIMIT_SEC" MODE="$MODE" \
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
    err = "timeout" if rc != 0 and rc in (142, 14, 1) and not raw else "no output (rc=%d)" % rc
    if rc in (142, 14):
        err = "timeout"
    skip = os.environ["MODE"] == "skip-heal"
    rec = {"stl": os.environ["STL"], "mode": os.environ["MODE"], "triangles": 0, "importMs": 0,
           "importError": None, "facesImported": 0, "validImported": False, "unifyMs": 0,
           "facesUnified": 0, "validUnified": False,
           "healMs": None if skip else 0, "facesHealed": None if skip else 0,
           "validFinal": False, "validationIssues": [],
           "stepMs": 0, "stepBytes": 0, "stepPath": None, "reimportMs": 0,
           "reimportOk": False, "totalMs": float(os.environ["LIMIT"]) * 1000.0, "error": err}
elif int(os.environ["RC"]) != 0 and not rec.get("error"):
    rec["error"] = "exit %s" % os.environ["RC"]
rec["slug"] = os.environ["SLUG"]
rec["mesh"] = os.environ["MESH"]
rec["peakRssMb"] = round(int(os.environ["RSS"] or 0) / (1024 * 1024), 1)
print(json.dumps(rec))
' <"$TMP_OUT" >>"$RESULTS"
done

echo "wrote $n records to $RESULTS" >&2
