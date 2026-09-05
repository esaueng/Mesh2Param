# Trusted-main CI migration

## Scope and inventory

This is the first small migration stage. `trusted-vps.yml` adds serial contracts
schema-generation checks, TypeScript checks, unit tests and compilation, plus UI
TypeScript checks and unit tests. Test worker count is one; assertions and thresholds
are unchanged. Node 22.22.0 and pnpm 11.7.0 match existing CI. The UI currently
allows no test files, as its existing test command specifies.

| Workflow/job | Execution and reason |
| --- | --- |
| Trusted VPS packages | Protected-main push or main-only manual dispatch; no secrets, caches, downloaded artifacts, arbitrary refs, Python, Rust or container build |
| CI Quality (static) | Hosted PR/main; full lint/types/build/license/asset gates compile Rust/WASM and load Python/CAD dependencies |
| CI Quality (frontend) | Hosted PR/main; retains contracts/UI tests and web coverage during this measurement stage |
| CI Quality (backend) | Hosted PR/main; native CAD dependencies and coverage need capacity measurements |
| CI Quality (browser) | Hosted PR/main; Chromium system dependencies and existing performance thresholds need measurements |
| CI Rust core | Hosted PR/main; Rust 1.96.0, WASM, clippy, corpus scoreboard and kernel tests need measurements |
| CI Containers | Hosted PR/main; native/web image builds, corpus and Compose security checks need measurements |
| Cloudflare verify/deploy | Unchanged; verification builds Rust/WASM, deploy uses Cloudflare credentials and stays hosted |
| VPS pilot | Existing private-repository probe, unchanged; not a replacement for ordinary CI |

No existing check name, trigger, coverage threshold or deployment gate is removed.
The small package checks intentionally overlap hosted checks until a real VPS main
run proves capacity. This PR does not resolve hosted PR billing failures. No macOS
or Windows workflows currently exist. Other existing pins include Python 3.12.11,
uv 0.11.28, and wasm-pack 0.15.0; none are changed.

## Trust and isolation

The job selects group `ci-trusted-main`, label `ci-small`, and checks runner identity
`ci-vm-1441561`, the non-root `ci-runner` user, rootless Docker, unwritable runner
binaries, and empty Docker/session sentinels. It checks out only the triggering SHA
with persisted credentials disabled. All actions reuse reviewed commit pins from
existing repository workflows. Only `contents: read` is granted; no deployment
credentials or remote caches/artifacts are consumed.

There is one listener/job slot across the whole machine. Repository concurrency is
only an additional queue guard; it cannot enforce cross-repository serialization.
The infrastructure's existing `ci.slice` imposes one CPU, 3 GiB aggregate memory and
no swap on the 4 GiB VPS. Node gets a 1536 MiB heap cap and tests use one worker.
This does not prove heavy jobs fit. The existing rootless Docker socket belongs to
CI; no rootful/host Docker socket, sudo or privileged containers are used.

The infrastructure's session service stops remaining processes and Docker and runs
its guarded reset between jobs. This workflow only writes sentinels; it never
prunes or deletes host data. Consult the current infrastructure
[README](https://github.com/petergstfsn/ci-server/blob/main/README.md) and
[security runbook](https://github.com/petergstfsn/ci-server/blob/main/docs/public-repositories.md).

## Activation is blocked pending protection and merge

Live inspection on 2026-09-05 found one online idle organization runner, this
repository already selected in group 6, and only `vps-pilot.yml@refs/heads/main`
allowed for this repository. GitHub reports `main` as `protected: false`.
Protection and effective-rules endpoints return a plan-related HTTP 403.
No runner allowlist or branch settings were changed. No VPS run was dispatched.

Before activation, verify main requires PR-based changes and passing checks,
applies to administrators, and disallows force pushes and deletion. Review any
ruleset bypass actors as well. A 403 or `ref_protected` alone is not proof of those
settings. Do not purchase a plan, change visibility, bypass checks or relax runner
access as part of this migration. Resolve the protection blocker separately.

After an authorized merge, verify the reviewed workflow is on protected main and
refresh the group configuration. Keep selected repository access and all unrelated
workflow entries unchanged. Replace exactly this existing entry:

```text
esaueng/Mesh2Param/.github/workflows/vps-pilot.yml@refs/heads/main
```

with this entry:

```text
esaueng/Mesh2Param/.github/workflows/trusted-vps.yml@refs/heads/main
```

Use the group's `selected_workflows` update with its freshly read full list. Keep
`restricted_to_workflows: true`, `visibility: selected`, and the selected repository
list unchanged. Replacing the old pilot entry retires that probe's access rather
than adding a second allowed workflow. Never add a branch/PR ref or temporarily
broaden the policy. Read back the exact group and repository lists after updating.
Do not activate before protection and the merge are verified.

## Real-run validation after activation

Dispatch `trusted-vps.yml` on `main`. Check the GitHub job's runner ID/name/group,
logs and outcome; do not infer success from an online runner. Per-command GNU time
reports elapsed time and maximum RSS in the seven-day evidence artifact. Start/end
UTC timestamps, disk usage and readable `ci.slice` memory peaks/events are included.
Slice peaks can include earlier jobs; per-command RSS is not whole-machine memory.

After completion, use the infrastructure's read-only diagnostics to verify disk
cleanup, one listener, no Docker leftovers or OOM kills, and the configured aggregate
limits. A job cannot prove cleanup that happens after it exits. Run a second
main dispatch and confirm both sentinel checks pass. Compare GitHub job intervals
with any other organization jobs to verify no overlap on the single runner. Record
both run URLs, elapsed times, memory observations and cleanup diagnostics here before
claiming this migration is activated and validated. Do not launch full CAD/Rust,
browser or container suites until separately measured and approved for this host.

## Rollback

Revoke only this workflow's exact group allowlist entry after draining its job, or
revert this PR through review. Existing hosted checks are unchanged and remain the
validation path; billing restrictions may still prevent them from starting. An
alternative reviewed rollback can move the optional package job to `ubuntu-24.04`
and remove its VPS-only identity/evidence steps. Preserve its commands and pins.
Deployment behavior remains unchanged in either case.
