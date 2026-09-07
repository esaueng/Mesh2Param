# Hosted allowance fallback

`ci.yml` calls `ci-jobs.yml` at an immutable commit. GitHub evaluates the runner
expression before scheduling each matrix job; there is no hosted selector or
aggregate job blocking the self-hosted path.

Only **Quality (frontend)** and **Quality (backend)** can move to the approved
Linux VPS. They run the same commands, assertions, coverage, and 60-minute timeout.
Static/WebAssembly builds, browser acceptance, Rust core, and Containers remain
hosted. The VPS cannot enforce the container suite's per-container cgroup limits;
no assertion or protection is relaxed. Browser system dependency installation also
requires privileges unavailable to its runner. Whole-pipeline completion can still
be blocked by hosted allowance exhaustion.

The management controller in the CI infrastructure project sets the repository
variable `CI_RUNNER_MODE` to `hosted` or `self-hosted`. Missing or unrecognized
values select hosted. A separate operator-managed repository variable,
`CI_TRUSTED_ACTOR`, identifies the approved contributor; an empty value never
enables self-hosted execution. The controller does not grant contributor trust.

Self-hosted routing also requires the exact repository, matching initiating and
rerun actors, and either a main push or a same-repository PR authored by the
approved contributor using GitHub's PR merge ref. Forks, other contributors,
bot-authored PRs, and reruns by other actors remain hosted. No caller inputs,
checkout overrides, or inherited secrets are accepted. Checkout credentials are
not persisted. Package caches are separated by runner environment.

The existing runner group must admit this repository and **the exact
`ci-jobs.yml@SHA` used by the caller**, retaining selected-repository and
selected-workflow restrictions. Labels do not grant access. Do not add PR refs
or arbitrary branches. Keep the runner's one-job limit, rootless Docker,
non-root identity, immutable binaries, and bounded cleanup.

## Review and activation

This change prepares routing; it does not set variables, modify the runner group,
start a controller timer, merge, or deploy. The first server run must validate both
compatible jobs and measure duration/memory; local workflow tests do not establish
VPS capacity. Review the immutable workflow commit, add that exact allowlist ref,
configure the trusted actor, then enable the controller after approval. Already
queued jobs retain their original runner assignment; submit a new run to test a
new selection. A busy/offline VPS queues eligible jobs rather than skipping them.

The reusable call changes check context display names to `checks / Quality (...)`,
`checks / Rust core`, and `checks / Containers`; review required-check configuration
where available. No check is removed. Updating the reusable workflow later needs
a reviewed new commit, caller pin, and allowlist change; editing the local file
alone does not change execution.

Rollback: stop the management timer, set `CI_RUNNER_MODE=hosted`, and allow current
jobs to finish. Remove the runner allowlist entry only after consumers stop using
it. A code rollback restores the original CI file through a PR. No production
deployment workflow is changed.
