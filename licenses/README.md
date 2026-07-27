# License compliance bundle

Mesh2Param original source is licensed under Apache-2.0; the canonical project text is the root
[`LICENSE`](../LICENSE). This directory contains required license texts for native components whose
terms are not replaced by the project license.

| File | Applies to | Canonical source |
| --- | --- | --- |
| `OCCT-LGPL-2.1.txt` | OCCT 7.9.3 shared libraries bundled in `cadquery-ocp` | [OCCT V7_9_3](https://github.com/Open-Cascade-SAS/OCCT/blob/V7_9_3/LICENSE_LGPL_21.txt) |
| `OCCT-LGPL-EXCEPTION-1.0.txt` | Additional permission for OCCT header material in object code | [OCCT V7_9_3 exception](https://github.com/Open-Cascade-SAS/OCCT/blob/V7_9_3/OCCT_LGPL_EXCEPTION.txt) |
| `CASADI-LGPL-3.0-or-later.txt` | Generic LGPL-3.0-or-later text for CasADi 3.7.2 and the platform-constrained libvips bundle used by Wrangler development tooling | [GNU LGPL 3.0](https://www.gnu.org/licenses/lgpl-3.0.txt) |
| `overrides.toml` | Audited corrections for incomplete or non-SPDX package metadata | Source URLs and a reason are mandatory per override |

The `cadquery-ocp` wheel declares its Python bindings as Apache-2.0 and also contains OCCT shared
libraries (`libTK*.so`, `.dylib`, or DLL equivalents). Those OCCT libraries are LGPL-2.1-only with
the Open CASCADE exception; both layers are recorded. CasADi's package metadata says LGPLv3+, and
the upstream 3.7.2 text permits version 3 or any later version. The existing Wrangler development
dependency installs one of the platform-constrained `@img/sharp-libvips-*` packages locked at
version 1.2.4. Those packages declare LGPL-3.0-or-later and contain libvips 8.17.3 plus their
recorded dynamic dependencies. Every locked platform variant is explicitly reviewed in policy but
remains development tooling rather than a Mesh2Param application runtime dependency.

Run the standard-library-only checker from the repository root after installing both ecosystems:

```sh
uv run --extra dev python scripts/check_licenses.py
```

The checker:

- audits every installed Python distribution and every package in pnpm's installed virtual store;
- rejects unresolved or non-allowlisted licenses and unreviewed GPL/AGPL/SSPL/BUSL/CC-BY-NC
  dependencies;
- permits LGPL only for the explicitly reviewed OCCT, CasADi, and
  platform-constrained Wrangler libvips packages;
- omits OS/architecture-constrained Python dependencies and platform-constrained JavaScript
  packages from the generated cross-platform notice inventory while still auditing their licenses;
- verifies hashes of the canonical project, OCCT, and CasADi license texts;
- rejects the GPL-bearing `jsonschema[format]` dependency path;
- checks that the generated table in `THIRD_PARTY_NOTICES.md` is current.

When adding a dependency, prefer SPDX metadata. Add an override only when upstream metadata is
missing or cannot express a bundled component, and include the exact package, effective license,
upstream source, and reason. Never use an override to make an incompatible license appear
permissive.

Redistributors of binary wheels, containers, or installers must make their own compliance
determination for the form they ship, including source-availability and relinking obligations for
LGPL components. The files here are not a substitute for legal advice.
