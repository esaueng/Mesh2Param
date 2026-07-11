# Contributing to Mesh2Param

Thank you for improving Mesh2Param. Contributions must preserve its evidence-first geometry and
security guarantees; a visually plausible result is not sufficient.

## Development setup

Use Python 3.12, Node 20+, pnpm 10+, and uv:

```sh
pnpm install --frozen-lockfile
XDG_CACHE_HOME=.cache uv sync --extra dev
pnpm db:migrate
pnpm dev
```

Do not commit `.env`, `.mesh2param-data`, browser reports, generated debug data, or secrets. Keep
unrelated working-tree changes intact.

## Change discipline

- CADGraph is the authoritative executable model. Never execute uploaded or model-generated Python.
- Never fabricate a STEP file, kernel-valid status, feature confidence, metric, benchmark, or test.
- Preserve source mesh bytes unchanged. Repair only a working copy through explicit, recorded steps.
- Reject kernel-invalid candidate histories before scoring.
- Keep search, memory, input, operation, and job bounds explicit and deterministic.
- A failed edit must retain the last valid geometry and report the feature/evidence that failed.
- Keep the browser mirror and backend revision authority separate; never silently resolve divergence.
- Add no runtime CDN or proprietary conversion service.

## Contracts and geometry changes

CADGraph changes start in `packages/contracts/schema/cadgraph.schema.json`. Update the Pydantic and
generated TypeScript artifacts through the existing generator, add migration coverage, and keep
canonical serialization byte-stable. A new feature operation requires:

1. schema/Pydantic/TypeScript support;
2. feature-level compiler errors and semantic topology handling;
3. valid OCCT build and rollback behavior;
4. STEP export and independent reimport tests;
5. generated CadQuery source coverage;
6. documentation of evidence and limitations.

Parser or worker changes must retain upload preflight, no-follow storage, bounded IPC, process
isolation, cancellation, cleanup, and the static trusted operation map.

## Frontend changes

Use the shared tokens and compact engineering-shell conventions. Preserve keyboard access, visible
focus, non-color status, reduced motion, responsive primary controls, stable camera behavior, and
both-theme contrast. Test rendered behavior, not only TypeScript compilation. Never label an
artifact valid before authoritative server validation completes.

## Tests and gates

Run the narrowest relevant test while iterating, then the affected package gates:

```sh
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm test:e2e
```

Geometry changes should run the applicable marked acceptance tests and deterministic sample
generation. Service changes should exercise API integration, cancellation/recovery, `/health`, and
`/ready`. UI changes should be inspected at the documented desktop, compact, and mobile sizes.

## Dependencies and licensing

Do not add AGPL, SSPL, BUSL, Commons Clause, CC-BY-NC, or unreviewed GPL dependencies. If a new
dependency is necessary:

1. pin it through the appropriate lockfile;
2. verify upstream license and source from a primary source;
3. run `uv run --extra dev python scripts/check_licenses.py`;
4. update `THIRD_PARTY_NOTICES.md` with `--write-notices`;
5. add a narrow override only for incomplete/non-SPDX metadata, never to conceal incompatibility;
6. include required attribution or license text.

OCCT and CasADi are reviewed LGPL components with specific redistribution obligations. Read
[`licenses/README.md`](licenses/README.md) before changing their packaging.

## Documentation and review

Update documentation with behavior changes and distinguish verified facts from planned work.
Security-sensitive reports belong in a private GitHub Security Advisory as described in
[SECURITY.md](SECURITY.md), not a public issue. A change is ready only when its claims are backed by
reproducible commands and artifacts.
