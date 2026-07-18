# PR-G2b calibration scope discrepancy

PR-G2b requires fillet-band-aware rejection codes to replace
`unsupported-freeform-remainder` for filleted prismatic sources. The accepted
PR-G2a calibration test in `tests/test_general_baseline.py` deliberately locks
all three general-parametric fixtures to that older generic rejection.

The PR-G2b allow-list permits only `tests/test_sections.py` under tests, so the
required behavior change cannot pass the existing test suite without modifying
a file outside the stated scope. Leaving the calibration test unchanged would
also make the G2b acceptance gate and the per-PR workflow mutually
inconsistent.

## Proposed plan amendment

- Add `tests/test_general_baseline.py` to the PR-G2b allow-list solely to update
  the calibrated rejection expectations for `spanner-filleted` and
  `spanner-filleted-embossed` to `fillet-band-detected` with measured radius
  evidence.
- Preserve the accepted `spanner-sharp` calibration at stage `segmentation`,
  code `unsupported-freeform-remainder`, and its exact message until PR-G2d
  reconstructs that fixture successfully.
- Do not broaden G2b to profile fitting, CADGraph emission, or fillet feature
  reconstruction; those remain assigned to PR-G2d and G3.

No G2b implementation has been made. Work stops here as required by Hard Rule
7 until the plan records the amended allow-list.
