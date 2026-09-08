# Optional small-VPS CI pilot

`VPS pilot` exercises one trusted, private-repository, Linux x86-64 runner.
It runs only on manual dispatch or pushes to `codex/vps-runner-pilot` while
this change is under review. It does not change the existing `CI` jobs or
Cloudflare deployment workflow. No repository secrets are passed to it.

The runner has one vCPU, a 3 GiB combined CI memory limit on a 4 GiB host,
and 32 GiB disposable CI storage. Two eligible matrix jobs verify that one
listener serializes work. Each verifies a fresh non-root home and empty
Docker daemon, builds/runs a tiny non-root scratch container, installs the
existing Python/Node/pnpm/uv pins, then runs the contracts package's existing
`verify` command with the frozen workspace lockfile.

Artifacts retain command elapsed time, max RSS, job timestamps, and disk
measurements for seven days. Command RSS is not whole-job or whole-machine
peak memory. These checks do not establish that full frontend, Python/CAD,
Rust, browser, or container acceptance suites fit this VPS. Existing coverage
and performance thresholds are unchanged.

This is a persistent trusted machine with Docker access equivalent to host
root. Keep fork PR workflows disabled; do not add `pull_request_target` or
untrusted PR execution. Workspaces, job homes, caches, and Docker state are
cleared between jobs by the infrastructure service, not by repository code.
Only one runner registration should exist on this host. The unique
`ci-vm-1441561` label avoids routing these tests to an unrelated runner.

To stop the pilot, stop dispatching it and disable this workflow. To move a
future selected CI job back, restore `runs-on: ubuntu-24.04` through a PR while
preserving the check name, commands, pins, and timeout. Hosted billing blockers
may still prevent that fallback from starting.
