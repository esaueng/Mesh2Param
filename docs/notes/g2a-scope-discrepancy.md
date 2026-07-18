# PR-G2a scope discrepancy

PR-G2a stopped before implementation because the checked-in plan and repository
state disagree in two ways that cannot be resolved inside the stated allow-list.

## Measured pre-change behavior

On 2026-07-18, using Python 3.12.13, pnpm 11.7.0, and the frozen dependency
sets, all three general-parametric fixtures matched the Section 1 calibration:

| Fixture | Exit | Stage | Code |
| --- | ---: | --- | --- |
| `spanner-sharp` | 2 | `segmentation` | `unsupported-freeform-remainder` |
| `spanner-filleted` | 2 | `segmentation` | `unsupported-freeform-remainder` |
| `spanner-filleted-embossed` | 2 | `segmentation` | `unsupported-freeform-remainder` |

Each emitted the recorded message: "automatic L-bracket inference requires
only plane and full-cylinder patches".

## Discrepancies

1. `ComparisonReport` already contains `p99_distance_mm`,
   `compare_meshes` already computes `np.quantile(combined, 0.99)`, and
   `to_dict()` already serializes the value as `distanceMm.p99`. Git history
   attributes this capability to commit `b6e2783`, so it is not new G2a work.
2. PR-G2a requires a runnable `pnpm general:baseline`, but `package.json`
   contains no `general:baseline` script and is not in the PR-G2a allow-list.
   The measured command fails with
   `ERR_PNPM_RECURSIVE_EXEC_FIRST_FAIL: Command "general:baseline" not found`.
   Registering `scripts/run_general_baseline.py` therefore requires an
   out-of-scope `package.json` change.

## Proposed plan amendment

- Add `package.json` to the PR-G2a allow-list solely to register
  `general:baseline` as
  `uv run --frozen python scripts/run_general_baseline.py`.
- Reword the P99 deliverable from implementation to regression coverage:
  preserve the existing calculation and serialization, and add calibration
  tests that lock its deterministic value and artifact representation.
- Keep the remaining PR-G2a goals unchanged: parametric surface-distribution
  gating, three-fixture structured-rejection calibration, the general faceted
  baseline runner, and a measured baseline table in the reconstruction plan.

No source mesh, fixture manifest, sample artifact, generated contract source,
or runtime dependency was changed while recording this proposal.
