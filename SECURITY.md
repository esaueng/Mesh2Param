# Security policy

## Supported versions

Mesh2Param is pre-1.0. Security fixes are applied to the current `main` branch. Historical commits,
forks, locally modified containers, and unsupported deployment configurations are not maintained by
this project.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use the repository's **Security →
Advisories → Report a vulnerability** flow to create a private GitHub Security Advisory for
`esaueng/Mesh2Param`. Include:

- affected commit/version and platform;
- attack prerequisites and trust boundary;
- minimal reproduction or malformed input (privately attached);
- actual and expected behavior;
- impact, including confidentiality/integrity/availability;
- any proposed mitigation.

Do not include secrets, personal data, customer models, or third-party confidential material. If
the private advisory flow is unavailable, disclose only that fact in a minimal public issue and ask
the maintainer to establish a private channel; do not publish exploit details.

Maintainers should acknowledge a complete report, reproduce it in an isolated environment, assign
severity based on demonstrated impact, coordinate a fix and release, and credit the reporter if
requested. No response-time or bounty promise is made.

## Security boundary

The local profile has no authentication and binds to loopback. It must not be exposed directly to an
untrusted network. Remote deployments require a trusted TLS/authentication boundary in front of the
single-origin web/API service and exact host/origin configuration.

Mesh uploads, CADGraph documents, project files, and generated artifacts are untrusted data.
Mesh2Param does not execute uploaded scripts or generated CadQuery source. Relevant controls and
deployment requirements are documented in [docs/security.md](docs/security.md).

## Out of scope

- social engineering, denial-of-service claims without a reproducible bound bypass, or scanner-only
  output without an affected path;
- vulnerabilities in unsupported third-party forks or modified deployments;
- attacks requiring prior arbitrary code execution as the same OS account, unless they cross a
  documented isolation boundary;
- license-compliance questions (use the notices and dependency checker instead).

Good-faith research should minimize data access and service disruption, use only systems and models
you are authorized to test, and give maintainers reasonable time to remediate before disclosure.
