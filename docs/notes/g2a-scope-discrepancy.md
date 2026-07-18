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

## Follow-up after the plan amendment

Commit `35baf26` resolved the original conflicts by adding `package.json` to
the G2a allow-list, treating P99 as regression coverage, and defining the
surface audit against measured OCCT types. The focused G2a implementation then
passed its eight tests, typecheck, and lint, and `pnpm general:baseline`
successfully recorded all three faceted conversions.

The required full gate stopped on two pre-existing repository inconsistencies:

1. `pnpm licenses:check` rejects
   `@img/sharp-libvips-darwin-arm64@1.2.4` as `LGPL-3.0-or-later` and reports a
   stale `THIRD_PARTY_NOTICES.md`. The unchanged dependency path is
   `wrangler@4.110.0` -> `miniflare` -> `sharp@0.34.5` -> the platform libvips
   package. G2a added no dependency or lockfile change.
2. `pnpm samples:check` reports the manifest and metadata files for all ten
   generated samples as changed. A direct diff shows geometry and artifact
   hashes are identical; only STEP `volumeTolerance` changes. For the
   rectangular-block sample it moves from `0.0144` to `0.072` because commit
   `b780b54` raised the current validation tolerance from one to five parts per
   million without regenerating the committed sample metadata.

License policy/notices and `samples/generated/` are outside the G2a allow-list,
and the task explicitly prohibits changing existing sample artifacts. G2a
therefore stops without weakening either gate. The prerequisites need separate
review: either select a Wrangler dependency set that passes the existing
license policy or explicitly review the LGPL package, and reconcile the
committed sample tolerance with the current five-ppm validation contract.

## Resolution after explicit continuation

The user authorized resolving the measured prerequisites and continuing the
plan. Commit `86fc91b` added the narrow prerequisite files to the G2a
allow-list. The implementation then:

- kept one-part-per-million STEP volume tolerance for analytic surfaces while
  retaining five parts per million when source or reimport geometry contains
  an exact freeform surface;
- explicitly reviewed and documented the existing platform-constrained
  libvips 8.17.3 bundle used by Wrangler development tooling, without changing
  the dependency graph; and
- regenerated only the dependency inventory in `THIRD_PARTY_NOTICES.md`.

The complete G2a gate subsequently passed: 100 committed sample files were
byte-stable, the license audit covered 88 Python and 391 JavaScript records,
the focused suite passed 9 tests, the backend suite passed 260 tests with one
fixture-dependent skip, the managed-sandbox semaphore test passed unchanged
when rerun outside the sandbox, and the L-bracket geometry acceptance passed.
All three spanner CLI runs retained the calibrated
`segmentation` / `unsupported-freeform-remainder` rejection, and the repeated
general baseline reproduced the recorded normalized STEP hashes.
