# Third-party notices

Mesh2Param's original source is Apache-2.0. Third-party components remain under their respective
licenses; the Apache-2.0 project license does not relicense them. This notice is an engineering
inventory, not legal advice. A distributor is responsible for satisfying the licenses that apply to
the exact binaries and source it ships.

## Components requiring prominent treatment

| Component | Version in `uv.lock` | License | Use and source |
| --- | --- | --- | --- |
| Open CASCADE Technology (OCCT) | 7.9.3, embedded by `cadquery-ocp` 7.9.3.1.1 | LGPL-2.1-only with Open CASCADE exception 1.0 | Exact B-Rep construction, validation, STEP import/export, and tessellation. [OCCT source](https://github.com/Open-Cascade-SAS/OCCT/tree/V7_9_3). |
| CadQuery OCP bindings | 7.9.3.1.1 | Apache-2.0 for the bindings; bundled OCCT remains LGPL-2.1 with the exception | Python bindings distributed by [CadQuery/OCP](https://github.com/CadQuery/OCP/tree/7.9.3.1). |
| CasADi | 3.7.2 | LGPL-3.0-or-later | Transitive dependency of CadQuery. [CasADi source](https://github.com/casadi/casadi/tree/3.7.2). Mesh2Param does not call it directly. |
| libvips development bundle | libvips 8.17.3 in `@img/sharp-libvips-darwin-arm64` 1.2.4 | LGPL-3.0-or-later package declaration; bundled components retain their recorded licenses | Platform-constrained transitive dependency of the existing Wrangler/Miniflare development toolchain. [sharp-libvips source](https://github.com/lovell/sharp-libvips/tree/v1.2.4). It is not a Mesh2Param application runtime dependency. |
| OpenCAE reference | commit `a8aba0048dd21565b5b76357cfd9be62917cf6f6c` | Apache-2.0 | Generic shell organization, design-token approach, control density, and accessibility conventions informed the distinct Mesh2Param UI. |

The corresponding license texts are:

- Project and Apache-2.0 components: [`LICENSE`](LICENSE)
- OCCT: [`licenses/OCCT-LGPL-2.1.txt`](licenses/OCCT-LGPL-2.1.txt) and
  [`licenses/OCCT-LGPL-EXCEPTION-1.0.txt`](licenses/OCCT-LGPL-EXCEPTION-1.0.txt)
- LGPL-3.0-or-later components (CasADi and the Wrangler libvips development
  bundle):
  [`licenses/CASADI-LGPL-3.0-or-later.txt`](licenses/CASADI-LGPL-3.0-or-later.txt)

OCCT and CasADi are dynamically loaded native libraries in the Python environment. The libvips
bundle is loaded only by platform-specific development tooling. If you redistribute wheels,
containers, installers, development environments, or another binary bundle, preserve these notices
and license texts and review the applicable corresponding-source, relinking/replacement, reverse
engineering, and modification requirements. Mesh2Param does not modify these components.

## Direct dependency summary

| Area | Dependencies | Licenses |
| --- | --- | --- |
| Geometry/runtime | CadQuery, cadquery-ocp, trimesh, NumPy, SciPy, Shapely, NetworkX | Apache-2.0; OCCT LGPL-2.1 + exception; MIT; BSD-family and bundled permissive notices |
| API/runtime | FastAPI, Pydantic Settings, SQLAlchemy, Uvicorn | MIT and BSD-3-Clause |
| Browser/runtime | React, React DOM, Three.js, R3F, Drei, Dexie, Immer, Lucide, Zustand | MIT, Apache-2.0, and ISC |
| Browser geometry | `@mesh2param/core-wasm`, the workspace Rust core compiled with `wasm-bindgen` | Apache-2.0, with the Remus kernel crates recorded under the Rust core row |
| Fonts | IBM Plex Sans and IBM Plex Mono through `@fontsource` | SIL Open Font License 1.1 |
| Rust core | Remus kernel crates (`remus-io`, `remus-math`, `remus-operations`, `remus-topology`), serde, serde_json, thiserror | Apache-2.0 and MIT OR Apache-2.0 |
| Schema/runtime | Ajv, ajv-formats | MIT |
| Development/test | Vite, TypeScript, ESLint, Vitest, Testing Library, Playwright, pytest, mypy, Ruff, jsonschema | MIT, Apache-2.0, BSD-family, and MPL-2.0 transitive components |

`jsonschema[format-nongpl]` is used deliberately. It installs permissively licensed RFC validators
instead of the `rfc3987` GPL-3.0+ dependency pulled by `jsonschema[format]`.

## Installed dependency inventory

This table is generated from the active uv environment and pnpm installation. Peer-resolution paths
are deduplicated by ecosystem, package, version, and effective license. Overrides are narrow,
source-linked, and reviewed in [`licenses/overrides.toml`](licenses/overrides.toml).
Platform-constrained pnpm packages (`os`, `cpu`, or `libc`) remain policy-audited when installed but
are omitted from this cross-platform table; distributors must audit the exact target installation.

<!-- BEGIN GENERATED DEPENDENCY INVENTORY -->

| Ecosystem | Package | Version | Declared/effective license |
| --- | --- | --- | --- |
| javascript | @adobe/css-tools | 4.5.0 | MIT |
| javascript | @apidevtools/json-schema-ref-parser | 11.9.3 | MIT |
| javascript | @asamuzakjp/css-color | 5.1.11 | MIT |
| javascript | @asamuzakjp/dom-selector | 7.1.1 | MIT |
| javascript | @asamuzakjp/generational-cache | 1.0.1 | MIT |
| javascript | @asamuzakjp/nwsapi | 2.3.9 | MIT |
| javascript | @babel/code-frame | 7.29.7 | MIT |
| javascript | @babel/compat-data | 7.29.7 | MIT |
| javascript | @babel/core | 7.29.7 | MIT |
| javascript | @babel/generator | 7.29.7 | MIT |
| javascript | @babel/helper-compilation-targets | 7.29.7 | MIT |
| javascript | @babel/helper-globals | 7.29.7 | MIT |
| javascript | @babel/helper-module-imports | 7.29.7 | MIT |
| javascript | @babel/helper-module-transforms | 7.29.7 | MIT |
| javascript | @babel/helper-string-parser | 7.29.7 | MIT |
| javascript | @babel/helper-validator-identifier | 7.29.7 | MIT |
| javascript | @babel/helper-validator-option | 7.29.7 | MIT |
| javascript | @babel/helpers | 7.29.7 | MIT |
| javascript | @babel/parser | 7.29.7 | MIT |
| javascript | @babel/runtime | 7.29.7 | MIT |
| javascript | @babel/template | 7.29.7 | MIT |
| javascript | @babel/traverse | 7.29.7 | MIT |
| javascript | @babel/types | 7.29.7 | MIT |
| javascript | @bcoe/v8-coverage | 1.0.2 | MIT |
| javascript | @bramus/specificity | 2.4.2 | MIT |
| javascript | @cloudflare/kv-asset-handler | 0.5.0 | MIT OR Apache-2.0 |
| javascript | @cloudflare/unenv-preset | 2.16.1 | MIT OR Apache-2.0 |
| javascript | @cspotcode/source-map-support | 0.8.1 | MIT |
| javascript | @csstools/color-helpers | 6.1.0 | MIT-0 |
| javascript | @csstools/css-calc | 3.2.1 | MIT |
| javascript | @csstools/css-color-parser | 4.1.9 | MIT |
| javascript | @csstools/css-parser-algorithms | 4.0.0 | MIT |
| javascript | @csstools/css-syntax-patches-for-csstree | 1.1.6 | MIT-0 |
| javascript | @csstools/css-tokenizer | 4.0.0 | MIT |
| javascript | @dimforge/rapier3d-compat | 0.12.0 | Apache-2.0 |
| javascript | @eslint-community/eslint-utils | 4.9.1 | MIT |
| javascript | @eslint-community/regexpp | 4.12.2 | MIT |
| javascript | @eslint/config-array | 0.23.5 | Apache-2.0 |
| javascript | @eslint/config-helpers | 0.6.0 | Apache-2.0 |
| javascript | @eslint/core | 1.2.1 | Apache-2.0 |
| javascript | @eslint/js | 10.0.1 | MIT |
| javascript | @eslint/object-schema | 3.0.5 | Apache-2.0 |
| javascript | @eslint/plugin-kit | 0.7.2 | Apache-2.0 |
| javascript | @exodus/bytes | 1.15.1 | MIT |
| javascript | @fontsource/ibm-plex-mono | 5.3.0 | OFL-1.1 |
| javascript | @fontsource/ibm-plex-sans | 5.3.0 | OFL-1.1 |
| javascript | @humanfs/core | 0.19.2 | Apache-2.0 |
| javascript | @humanfs/node | 0.16.8 | Apache-2.0 |
| javascript | @humanfs/types | 0.15.0 | Apache-2.0 |
| javascript | @humanwhocodes/module-importer | 1.0.1 | Apache-2.0 |
| javascript | @humanwhocodes/retry | 0.4.3 | Apache-2.0 |
| javascript | @img/colour | 1.1.0 | MIT |
| javascript | @jridgewell/gen-mapping | 0.3.13 | MIT |
| javascript | @jridgewell/remapping | 2.3.5 | MIT |
| javascript | @jridgewell/resolve-uri | 3.1.2 | MIT |
| javascript | @jridgewell/sourcemap-codec | 1.5.5 | MIT |
| javascript | @jridgewell/trace-mapping | 0.3.31 | MIT |
| javascript | @jridgewell/trace-mapping | 0.3.9 | MIT |
| javascript | @jsdevtools/ono | 7.1.3 | MIT |
| javascript | @mediapipe/tasks-vision | 0.10.17 | Apache-2.0 |
| javascript | @monogrid/gainmap-js | 3.4.0 | MIT |
| javascript | @oxc-project/types | 0.139.0 | MIT |
| javascript | @playwright/test | 1.61.1 | Apache-2.0 |
| javascript | @poppinss/colors | 4.1.6 | MIT |
| javascript | @poppinss/dumper | 0.6.5 | MIT |
| javascript | @poppinss/exception | 1.2.3 | MIT |
| javascript | @react-three/drei | 10.7.7 | MIT |
| javascript | @react-three/fiber | 9.6.1 | MIT |
| javascript | @rolldown/pluginutils | 1.0.1 | MIT |
| javascript | @sindresorhus/is | 7.2.0 | MIT |
| javascript | @speed-highlight/core | 1.2.17 | CC0-1.0 |
| javascript | @standard-schema/spec | 1.1.0 | MIT |
| javascript | @testing-library/dom | 10.4.1 | MIT |
| javascript | @testing-library/jest-dom | 6.9.1 | MIT |
| javascript | @testing-library/react | 16.3.2 | MIT |
| javascript | @testing-library/user-event | 14.6.1 | MIT |
| javascript | @tweenjs/tween.js | 23.1.3 | MIT |
| javascript | @types/aria-query | 5.0.4 | MIT |
| javascript | @types/chai | 5.2.3 | MIT |
| javascript | @types/deep-eql | 4.0.2 | MIT |
| javascript | @types/draco3d | 1.4.10 | MIT |
| javascript | @types/esrecurse | 4.3.1 | MIT |
| javascript | @types/estree | 1.0.9 | MIT |
| javascript | @types/json-schema | 7.0.15 | MIT |
| javascript | @types/lodash | 4.17.24 | MIT |
| javascript | @types/node | 26.1.1 | MIT |
| javascript | @types/offscreencanvas | 2019.7.3 | MIT |
| javascript | @types/react | 19.2.17 | MIT |
| javascript | @types/react-dom | 19.2.3 | MIT |
| javascript | @types/react-reconciler | 0.28.9 | MIT |
| javascript | @types/stats.js | 0.17.4 | MIT |
| javascript | @types/three | 0.185.1 | MIT |
| javascript | @types/webxr | 0.5.24 | MIT |
| javascript | @typescript-eslint/eslint-plugin | 8.64.0 | MIT |
| javascript | @typescript-eslint/parser | 8.64.0 | MIT |
| javascript | @typescript-eslint/project-service | 8.64.0 | MIT |
| javascript | @typescript-eslint/scope-manager | 8.64.0 | MIT |
| javascript | @typescript-eslint/tsconfig-utils | 8.64.0 | MIT |
| javascript | @typescript-eslint/type-utils | 8.64.0 | MIT |
| javascript | @typescript-eslint/types | 8.64.0 | MIT |
| javascript | @typescript-eslint/typescript-estree | 8.64.0 | MIT |
| javascript | @typescript-eslint/utils | 8.64.0 | MIT |
| javascript | @typescript-eslint/visitor-keys | 8.64.0 | MIT |
| javascript | @use-gesture/core | 10.3.1 | MIT |
| javascript | @use-gesture/react | 10.3.1 | MIT |
| javascript | @vitejs/plugin-react | 6.0.3 | MIT |
| javascript | @vitest/coverage-v8 | 4.1.10 | MIT |
| javascript | @vitest/expect | 4.1.10 | MIT |
| javascript | @vitest/mocker | 4.1.10 | MIT |
| javascript | @vitest/pretty-format | 4.1.10 | MIT |
| javascript | @vitest/runner | 4.1.10 | MIT |
| javascript | @vitest/snapshot | 4.1.10 | MIT |
| javascript | @vitest/spy | 4.1.10 | MIT |
| javascript | @vitest/utils | 4.1.10 | MIT |
| javascript | acorn | 8.17.0 | MIT |
| javascript | acorn-jsx | 5.3.2 | MIT |
| javascript | ajv | 6.15.0 | MIT |
| javascript | ajv | 8.20.0 | MIT |
| javascript | ajv-formats | 3.0.1 | MIT |
| javascript | ansi-regex | 5.0.1 | MIT |
| javascript | ansi-regex | 6.2.2 | MIT |
| javascript | ansi-styles | 5.2.0 | MIT |
| javascript | ansi-styles | 6.2.3 | MIT |
| javascript | argparse | 2.0.1 | Python-2.0 |
| javascript | aria-query | 5.3.0 | Apache-2.0 |
| javascript | aria-query | 5.3.2 | Apache-2.0 |
| javascript | assertion-error | 2.0.1 | MIT |
| javascript | ast-v8-to-istanbul | 1.0.5 | MIT |
| javascript | balanced-match | 4.0.4 | MIT |
| javascript | base64-js | 1.5.1 | MIT |
| javascript | baseline-browser-mapping | 2.10.42 | Apache-2.0 |
| javascript | bidi-js | 1.0.3 | MIT |
| javascript | blake3-wasm | 2.1.5 | MIT |
| javascript | brace-expansion | 5.0.7 | MIT |
| javascript | browserslist | 4.28.5 | MIT |
| javascript | buffer | 6.0.3 | MIT |
| javascript | camera-controls | 3.1.2 | MIT |
| javascript | caniuse-lite | 1.0.30001803 | CC-BY-4.0 |
| javascript | chai | 6.2.2 | MIT |
| javascript | chalk | 5.6.2 | MIT |
| javascript | cliui | 9.0.1 | ISC |
| javascript | concurrently | 10.0.3 | MIT |
| javascript | convert-source-map | 2.0.0 | MIT |
| javascript | cookie | 1.1.1 | MIT |
| javascript | cross-env | 7.0.3 | MIT |
| javascript | cross-spawn | 7.0.6 | MIT |
| javascript | css-tree | 3.2.1 | MIT |
| javascript | css.escape | 1.5.1 | MIT |
| javascript | csstype | 3.2.3 | MIT |
| javascript | data-urls | 7.0.0 | MIT |
| javascript | debug | 4.4.3 | MIT |
| javascript | decimal.js | 10.6.0 | MIT |
| javascript | deep-is | 0.1.4 | MIT |
| javascript | dequal | 2.0.3 | MIT |
| javascript | detect-gpu | 5.0.70 | MIT |
| javascript | detect-libc | 2.1.2 | Apache-2.0 |
| javascript | dexie | 4.4.4 | Apache-2.0 |
| javascript | dom-accessibility-api | 0.5.16 | MIT |
| javascript | dom-accessibility-api | 0.6.3 | MIT |
| javascript | draco3d | 1.5.7 | Apache-2.0 |
| javascript | electron-to-chromium | 1.5.389 | ISC |
| javascript | emoji-regex | 10.6.0 | MIT |
| javascript | entities | 8.0.0 | BSD-2-Clause |
| javascript | error-stack-parser-es | 1.0.5 | MIT |
| javascript | es-module-lexer | 2.3.1 | MIT |
| javascript | esbuild | 0.28.1 | MIT |
| javascript | escalade | 3.2.0 | MIT |
| javascript | escape-string-regexp | 4.0.0 | MIT |
| javascript | eslint | 10.7.0 | MIT |
| javascript | eslint-plugin-react-hooks | 7.1.1 | MIT |
| javascript | eslint-scope | 9.1.2 | BSD-2-Clause |
| javascript | eslint-visitor-keys | 3.4.3 | Apache-2.0 |
| javascript | eslint-visitor-keys | 5.0.1 | Apache-2.0 |
| javascript | espree | 11.2.0 | BSD-2-Clause |
| javascript | esquery | 1.7.0 | BSD-3-Clause |
| javascript | esrecurse | 4.3.0 | BSD-2-Clause |
| javascript | estraverse | 5.3.0 | BSD-2-Clause |
| javascript | estree-walker | 3.0.3 | MIT |
| javascript | esutils | 2.0.3 | BSD-2-Clause |
| javascript | expect-type | 1.4.0 | Apache-2.0 |
| javascript | fake-indexeddb | 6.2.5 | Apache-2.0 |
| javascript | fast-deep-equal | 3.1.3 | MIT |
| javascript | fast-json-stable-stringify | 2.1.0 | MIT |
| javascript | fast-levenshtein | 2.0.6 | MIT |
| javascript | fast-uri | 3.1.4 | BSD-3-Clause |
| javascript | fdir | 6.5.0 | MIT |
| javascript | fflate | 0.6.10 | MIT |
| javascript | fflate | 0.8.3 | MIT |
| javascript | file-entry-cache | 8.0.0 | MIT |
| javascript | find-up | 5.0.0 | MIT |
| javascript | flat-cache | 4.0.1 | MIT |
| javascript | flatted | 3.4.2 | ISC |
| javascript | gensync | 1.0.0-beta.2 | MIT |
| javascript | get-caller-file | 2.0.5 | ISC |
| javascript | get-east-asian-width | 1.6.0 | MIT |
| javascript | glob-parent | 6.0.2 | ISC |
| javascript | glsl-noise | 0.0.0 | MIT |
| javascript | has-flag | 4.0.0 | MIT |
| javascript | hermes-estree | 0.25.1 | MIT |
| javascript | hermes-parser | 0.25.1 | MIT |
| javascript | hls.js | 1.6.16 | Apache-2.0 |
| javascript | html-encoding-sniffer | 6.0.0 | MIT |
| javascript | html-escaper | 2.0.2 | MIT |
| javascript | ieee754 | 1.2.1 | BSD-3-Clause |
| javascript | ignore | 5.3.2 | MIT |
| javascript | ignore | 7.0.5 | MIT |
| javascript | immediate | 3.0.6 | MIT |
| javascript | immer | 11.1.15 | MIT |
| javascript | imurmurhash | 0.1.4 | MIT |
| javascript | indent-string | 4.0.0 | MIT |
| javascript | is-extglob | 2.1.1 | MIT |
| javascript | is-glob | 4.0.3 | MIT |
| javascript | is-potential-custom-element-name | 1.0.1 | MIT |
| javascript | is-promise | 2.2.2 | MIT |
| javascript | isexe | 2.0.0 | ISC |
| javascript | istanbul-lib-coverage | 3.2.2 | BSD-3-Clause |
| javascript | istanbul-lib-report | 3.0.1 | BSD-3-Clause |
| javascript | istanbul-reports | 3.2.0 | BSD-3-Clause |
| javascript | its-fine | 2.0.0 | MIT |
| javascript | js-tokens | 10.0.0 | MIT |
| javascript | js-tokens | 4.0.0 | MIT |
| javascript | js-yaml | 4.3.0 | MIT |
| javascript | jsdom | 29.1.1 | MIT |
| javascript | jsesc | 3.1.0 | MIT |
| javascript | json-buffer | 3.0.1 | MIT |
| javascript | json-schema-to-typescript | 15.0.4 | MIT |
| javascript | json-schema-traverse | 0.4.1 | MIT |
| javascript | json-schema-traverse | 1.0.0 | MIT |
| javascript | json-stable-stringify-without-jsonify | 1.0.1 | MIT |
| javascript | json5 | 2.2.3 | MIT |
| javascript | keyv | 4.5.4 | MIT |
| javascript | kleur | 4.1.5 | MIT |
| javascript | levn | 0.4.1 | MIT |
| javascript | lie | 3.3.0 | MIT |
| javascript | lightningcss | 1.32.0 | MPL-2.0 |
| javascript | locate-path | 6.0.0 | MIT |
| javascript | lodash | 4.18.1 | MIT |
| javascript | lru-cache | 11.5.2 | BlueOak-1.0.0 |
| javascript | lru-cache | 5.1.1 | ISC |
| javascript | lucide-react | 1.25.0 | ISC |
| javascript | lz-string | 1.5.0 | MIT |
| javascript | maath | 0.10.8 | MIT |
| javascript | magic-string | 0.30.21 | MIT |
| javascript | magicast | 0.5.3 | MIT |
| javascript | make-dir | 4.0.0 | MIT |
| javascript | mdn-data | 2.27.1 | CC0-1.0 |
| javascript | meshline | 3.3.1 | MIT |
| javascript | meshoptimizer | 1.1.1 | MIT |
| javascript | min-indent | 1.0.1 | MIT |
| javascript | miniflare | 4.20260714.0 | MIT |
| javascript | minimatch | 10.2.5 | BlueOak-1.0.0 |
| javascript | minimist | 1.2.8 | MIT |
| javascript | ms | 2.1.3 | MIT |
| javascript | nanoid | 3.3.15 | MIT |
| javascript | natural-compare | 1.4.0 | MIT |
| javascript | node-releases | 2.0.51 | MIT |
| javascript | obug | 2.1.4 | MIT |
| javascript | optionator | 0.9.4 | MIT |
| javascript | p-limit | 3.1.0 | MIT |
| javascript | p-locate | 5.0.0 | MIT |
| javascript | parse5 | 8.0.1 | MIT |
| javascript | path-exists | 4.0.0 | MIT |
| javascript | path-key | 3.1.1 | MIT |
| javascript | path-to-regexp | 6.3.0 | MIT |
| javascript | pathe | 2.0.3 | MIT |
| javascript | picocolors | 1.1.1 | ISC |
| javascript | picomatch | 4.0.5 | MIT |
| javascript | playwright | 1.61.1 | Apache-2.0 |
| javascript | playwright-core | 1.61.1 | Apache-2.0 |
| javascript | postcss | 8.5.19 | MIT |
| javascript | potpack | 1.0.2 | ISC |
| javascript | prelude-ls | 1.2.1 | MIT |
| javascript | prettier | 3.9.5 | MIT |
| javascript | pretty-format | 27.5.1 | MIT |
| javascript | promise-worker-transferable | 1.0.4 | Apache-2.0 |
| javascript | punycode | 2.3.1 | MIT |
| javascript | react | 19.2.7 | MIT |
| javascript | react-dom | 19.2.7 | MIT |
| javascript | react-is | 17.0.2 | MIT |
| javascript | react-use-measure | 2.1.7 | MIT |
| javascript | redent | 3.0.0 | MIT |
| javascript | require-from-string | 2.0.2 | MIT |
| javascript | rolldown | 1.1.5 | MIT |
| javascript | rxjs | 7.8.2 | Apache-2.0 |
| javascript | saxes | 6.0.0 | ISC |
| javascript | scheduler | 0.27.0 | MIT |
| javascript | semver | 6.3.1 | ISC |
| javascript | semver | 7.8.5 | ISC |
| javascript | sharp | 0.34.5 | Apache-2.0 |
| javascript | shebang-command | 2.0.0 | MIT |
| javascript | shebang-regex | 3.0.0 | MIT |
| javascript | shell-quote | 1.8.4 | MIT |
| javascript | siginfo | 2.0.0 | ISC |
| javascript | source-map-js | 1.2.1 | BSD-3-Clause |
| javascript | stackback | 0.0.2 | MIT |
| javascript | stats-gl | 2.4.2 | MIT |
| javascript | stats.js | 0.17.0 | MIT |
| javascript | std-env | 4.2.0 | MIT |
| javascript | string-width | 7.2.0 | MIT |
| javascript | strip-ansi | 7.2.0 | MIT |
| javascript | strip-indent | 3.0.0 | MIT |
| javascript | supports-color | 10.2.2 | MIT |
| javascript | supports-color | 7.2.0 | MIT |
| javascript | suspend-react | 0.1.3 | MIT |
| javascript | symbol-tree | 3.2.4 | MIT |
| javascript | three | 0.185.1 | MIT |
| javascript | three-mesh-bvh | 0.8.3 | MIT |
| javascript | three-stdlib | 2.36.1 | MIT |
| javascript | tinybench | 2.9.0 | MIT |
| javascript | tinyexec | 1.2.4 | MIT |
| javascript | tinyglobby | 0.2.17 | MIT |
| javascript | tinyrainbow | 3.1.0 | MIT |
| javascript | tldts | 7.4.9 | MIT |
| javascript | tldts-core | 7.4.9 | MIT |
| javascript | tough-cookie | 6.0.2 | BSD-3-Clause |
| javascript | tr46 | 6.0.0 | MIT |
| javascript | tree-kill | 1.2.2 | MIT |
| javascript | troika-three-text | 0.52.4 | MIT |
| javascript | troika-three-utils | 0.52.4 | MIT |
| javascript | troika-worker-utils | 0.52.0 | MIT |
| javascript | ts-api-utils | 2.5.0 | MIT |
| javascript | tslib | 2.8.1 | 0BSD |
| javascript | tunnel-rat | 0.1.2 | MIT |
| javascript | type-check | 0.4.0 | MIT |
| javascript | typescript | 5.9.3 | Apache-2.0 |
| javascript | typescript-eslint | 8.64.0 | MIT |
| javascript | undici | 7.28.0 | MIT |
| javascript | undici-types | 8.3.0 | MIT |
| javascript | unenv | 2.0.0-rc.24 | MIT |
| javascript | update-browserslist-db | 1.2.3 | MIT |
| javascript | uri-js | 4.4.1 | BSD-2-Clause |
| javascript | use-sync-external-store | 1.6.0 | MIT |
| javascript | utility-types | 3.11.0 | MIT |
| javascript | vite | 8.1.5 | MIT |
| javascript | vitest | 4.1.10 | MIT |
| javascript | w3c-xmlserializer | 5.0.0 | MIT |
| javascript | webgl-constants | 1.1.1 | MIT |
| javascript | webgl-sdf-generator | 1.1.1 | MIT |
| javascript | webidl-conversions | 8.0.1 | BSD-2-Clause |
| javascript | whatwg-mimetype | 5.0.0 | MIT |
| javascript | whatwg-url | 16.0.1 | MIT |
| javascript | which | 2.0.2 | ISC |
| javascript | why-is-node-running | 2.3.0 | MIT |
| javascript | word-wrap | 1.2.5 | MIT |
| javascript | workerd | 1.20260714.1 | Apache-2.0 |
| javascript | wrangler | 4.112.0 | MIT OR Apache-2.0 |
| javascript | wrap-ansi | 9.0.2 | MIT |
| javascript | ws | 8.21.0 | MIT |
| javascript | xml-name-validator | 5.0.0 | Apache-2.0 |
| javascript | xmlchars | 2.2.0 | MIT |
| javascript | y18n | 5.0.8 | ISC |
| javascript | yallist | 3.1.1 | ISC |
| javascript | yargs | 18.0.0 | MIT |
| javascript | yargs-parser | 22.0.0 | ISC |
| javascript | yocto-queue | 0.1.0 | MIT |
| javascript | youch | 4.1.0-beta.10 | MIT |
| javascript | youch-core | 0.3.3 | MIT |
| javascript | zod | 4.4.3 | MIT |
| javascript | zod-validation-error | 4.0.2 | MIT |
| javascript | zustand | 4.5.7 | MIT |
| javascript | zustand | 5.0.14 | MIT |
| python | Mako | 1.3.12 | MIT |
| python | MarkupSafe | 3.0.3 | BSD-3-Clause |
| python | PyYAML | 6.0.3 | MIT |
| python | Pygments | 2.20.0 | BSD-2-Clause |
| python | SQLAlchemy | 2.0.51 | MIT |
| python | aiohappyeyeballs | 2.7.1 | PSF-2.0 |
| python | aiohttp | 3.14.1 | Apache-2.0 AND MIT |
| python | aiosignal | 1.4.0 | Apache-2.0 |
| python | alembic | 1.18.5 | MIT |
| python | annotated-doc | 0.0.4 | MIT |
| python | annotated-types | 0.7.0 | MIT |
| python | anyio | 4.14.1 | MIT |
| python | arrow | 1.4.0 | Apache-2.0 |
| python | ast_serialize | 0.6.0 | MIT |
| python | attrs | 26.1.0 | MIT |
| python | cadquery | 2.8.0 | Apache-2.0 |
| python | cadquery-ocp | 7.9.3.1.1 | Apache-2.0 AND LGPL-2.1-only WITH OCCT-exception-1.0 |
| python | cadquery-ocp-proxy | 7.9.3.1.1 | Apache-2.0 |
| python | casadi | 3.7.2 | LGPL-3.0-or-later |
| python | certifi | 2026.6.17 | MPL-2.0 |
| python | click | 8.4.2 | BSD-3-Clause |
| python | contourpy | 1.3.3 | BSD-3-Clause |
| python | coverage | 7.15.2 | Apache-2.0 |
| python | cycler | 0.12.1 | BSD-3-Clause |
| python | ezdxf | 1.4.4 | MIT |
| python | fastapi | 0.139.2 | MIT |
| python | fonttools | 4.63.0 | MIT |
| python | fqdn | 1.5.1 | MPL-2.0 |
| python | frozenlist | 1.8.0 | Apache-2.0 |
| python | h11 | 0.16.0 | MIT |
| python | httpcore | 1.0.9 | BSD-3-Clause |
| python | httpx | 0.28.1 | BSD-3-Clause |
| python | idna | 3.18 | BSD-3-Clause |
| python | iniconfig | 2.3.0 | MIT |
| python | isoduration | 20.11.0 | ISC |
| python | jsonpointer | 3.1.1 | BSD-3-Clause |
| python | jsonschema | 4.26.0 | MIT |
| python | jsonschema-specifications | 2025.9.1 | MIT |
| python | kiwisolver | 1.5.0 | BSD-3-Clause |
| python | lark | 1.3.1 | MIT |
| python | librt | 0.13.0 | MIT |
| python | llvmlite | 0.48.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception |
| python | matplotlib | 3.11.0 | LicenseRef-Matplotlib |
| python | more-itertools | 11.1.0 | MIT |
| python | msgpack | 1.2.1 | Apache-2.0 |
| python | multidict | 6.7.1 | Apache-2.0 |
| python | multimethod | 1.12 | Apache-2.0 |
| python | mypy | 2.3.0 | MIT |
| python | mypy_extensions | 1.1.0 | MIT |
| python | networkx | 3.6.1 | BSD-3-Clause |
| python | nlopt | 2.10.0 | MIT |
| python | numba | 0.66.0 | BSD-3-Clause |
| python | numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| python | packaging | 26.2 | Apache-2.0 OR BSD-2-Clause |
| python | pathspec | 1.1.1 | MPL-2.0 |
| python | pillow | 12.3.0 | MIT-CMU |
| python | pluggy | 1.6.0 | MIT |
| python | propcache | 0.5.2 | Apache-2.0 |
| python | pydantic | 2.13.4 | MIT |
| python | pydantic-settings | 2.14.2 | MIT |
| python | pydantic_core | 2.46.4 | MIT |
| python | pyparsing | 3.3.2 | MIT |
| python | pytest | 9.1.1 | MIT |
| python | pytest-cov | 7.1.0 | MIT |
| python | python-dateutil | 2.9.0.post0 | BSD-3-Clause OR Apache-2.0 |
| python | python-dotenv | 1.2.2 | BSD-3-Clause |
| python | referencing | 0.37.0 | MIT |
| python | rfc3339-validator | 0.1.4 | MIT |
| python | rfc3986-validator | 0.1.1 | MIT |
| python | rfc3987-syntax | 1.1.0 | MIT |
| python | rpds-py | 2026.6.3 | MIT |
| python | ruff | 0.15.21 | MIT |
| python | runtype | 0.5.3 | MIT |
| python | scipy | 1.18.0 | BSD-3-Clause |
| python | shapely | 2.1.2 | BSD-3-Clause |
| python | six | 1.17.0 | MIT |
| python | starlette | 0.47.3 | BSD-3-Clause |
| python | trame | 3.13.2 | Apache-2.0 |
| python | trame-client | 3.13.2 | MIT |
| python | trame-common | 1.2.4 | Apache-2.0 |
| python | trame-components | 2.5.0 | Apache-2.0 |
| python | trame-server | 3.12.5 | Apache-2.0 |
| python | trame-vtk | 2.11.13 | BSD-3-Clause |
| python | trame-vuetify | 3.2.2 | MIT |
| python | trimesh | 4.12.2 | MIT |
| python | typing-inspection | 0.4.2 | MIT |
| python | typing_extensions | 4.16.0 | PSF-2.0 |
| python | tzdata | 2026.3 | Apache-2.0 |
| python | uri-template | 1.3.0 | MIT |
| python | uvicorn | 0.51.0 | BSD-3-Clause |
| python | vtk | 9.6.2 | BSD-3-Clause |
| python | webcolors | 25.10.0 | BSD-3-Clause |
| python | wslink | 2.5.7 | BSD-3-Clause |
| python | yarl | 1.24.2 | Apache-2.0 |

<!-- END GENERATED DEPENDENCY INVENTORY -->

## Rust

`crates/mesh2param-core` resolves its dependency graph through the committed `Cargo.lock`. The table
below is generated from `cargo metadata` and lists every resolved package except the workspace
members themselves, with the source Cargo resolved it from. Crates.io packages are identified by
name and version; git packages carry the exact commit Cargo pinned, not the branch or tag that
selected it.

The Remus geometry kernel crates (`remus-*`) come from
[esaueng/remus](https://github.com/esaueng/remus) at the revision pinned in
[`crates/mesh2param-core/Cargo.toml`](crates/mesh2param-core/Cargo.toml) and are Apache-2.0, the
same license as Mesh2Param's own source. Unlike OCCT, the Rust core links no LGPL component: every
crate below is under a permissive license. A crate that declares its terms only through a
`license-file` is recorded as `UNKNOWN` and fails the audit until it is reviewed and given an
override in [`licenses/overrides.toml`](licenses/overrides.toml).

<!-- BEGIN GENERATED RUST DEPENDENCY INVENTORY -->

| Crate | Version | Declared/effective license | Source | Repository |
| --- | --- | --- | --- | --- |
| bitflags | 2.13.1 | MIT OR Apache-2.0 | crates.io | https://github.com/bitflags/bitflags |
| bumpalo | 3.20.3 | MIT OR Apache-2.0 | crates.io | https://github.com/fitzgen/bumpalo |
| cfg-if | 1.0.4 | MIT OR Apache-2.0 | crates.io | https://github.com/rust-lang/cfg-if |
| console_error_panic_hook | 0.1.7 | Apache-2.0/MIT | crates.io | https://github.com/rustwasm/console_error_panic_hook |
| crc32fast | 1.5.1 | MIT OR Apache-2.0 | crates.io | https://github.com/srijs/rust-crc32fast |
| crossbeam-deque | 0.8.7 | MIT OR Apache-2.0 | crates.io | https://github.com/crossbeam-rs/crossbeam |
| crossbeam-epoch | 0.9.20 | MIT OR Apache-2.0 | crates.io | https://github.com/crossbeam-rs/crossbeam |
| crossbeam-utils | 0.8.22 | MIT OR Apache-2.0 | crates.io | https://github.com/crossbeam-rs/crossbeam |
| either | 1.18.0 | MIT OR Apache-2.0 | crates.io | https://github.com/rayon-rs/either |
| equivalent | 1.0.2 | Apache-2.0 OR MIT | crates.io | https://github.com/indexmap-rs/equivalent |
| flate2 | 1.1.10 | MIT OR Apache-2.0 | crates.io | https://github.com/rust-lang/flate2-rs |
| futures-core | 0.3.34 | MIT OR Apache-2.0 | crates.io | https://github.com/rust-lang/futures-rs |
| futures-task | 0.3.34 | MIT OR Apache-2.0 | crates.io | https://github.com/rust-lang/futures-rs |
| futures-util | 0.3.34 | MIT OR Apache-2.0 | crates.io | https://github.com/rust-lang/futures-rs |
| hashbrown | 0.17.1 | MIT OR Apache-2.0 | crates.io | https://github.com/rust-lang/hashbrown |
| indexmap | 2.14.1 | Apache-2.0 OR MIT | crates.io | https://github.com/indexmap-rs/indexmap |
| itoa | 1.0.18 | MIT OR Apache-2.0 | crates.io | https://github.com/dtolnay/itoa |
| js-sys | 0.3.103 | MIT OR Apache-2.0 | crates.io | https://github.com/wasm-bindgen/wasm-bindgen/tree/master/crates/js-sys |
| log | 0.4.34 | MIT OR Apache-2.0 | crates.io | https://github.com/rust-lang/log |
| memchr | 2.8.3 | Unlicense OR MIT | crates.io | https://github.com/BurntSushi/memchr |
| once_cell | 1.21.4 | MIT OR Apache-2.0 | crates.io | https://github.com/matklad/once_cell |
| pin-project-lite | 0.2.17 | Apache-2.0 OR MIT | crates.io | https://github.com/taiki-e/pin-project-lite |
| proc-macro2 | 1.0.107 | MIT OR Apache-2.0 | crates.io | https://github.com/dtolnay/proc-macro2 |
| quick-xml | 0.41.0 | MIT | crates.io | https://github.com/tafia/quick-xml |
| quote | 1.0.47 | MIT OR Apache-2.0 | crates.io | https://github.com/dtolnay/quote |
| rayon | 1.12.0 | MIT OR Apache-2.0 | crates.io | https://github.com/rayon-rs/rayon |
| rayon-core | 1.13.0 | MIT OR Apache-2.0 | crates.io | https://github.com/rayon-rs/rayon |
| remus-algo | 0.1.0 | Apache-2.0 | git+https://github.com/esaueng/remus#cbd1382f8ee3113ce1c42415308ab3488e641625 | https://github.com/esaueng/remus |
| remus-blend | 0.1.0 | Apache-2.0 | git+https://github.com/esaueng/remus#cbd1382f8ee3113ce1c42415308ab3488e641625 | https://github.com/esaueng/remus |
| remus-check | 0.1.0 | Apache-2.0 | git+https://github.com/esaueng/remus#cbd1382f8ee3113ce1c42415308ab3488e641625 | https://github.com/esaueng/remus |
| remus-geometry | 0.1.0 | Apache-2.0 | git+https://github.com/esaueng/remus#cbd1382f8ee3113ce1c42415308ab3488e641625 | https://github.com/esaueng/remus |
| remus-heal | 0.1.0 | Apache-2.0 | git+https://github.com/esaueng/remus#cbd1382f8ee3113ce1c42415308ab3488e641625 | https://github.com/esaueng/remus |
| remus-io | 0.1.0 | Apache-2.0 | git+https://github.com/esaueng/remus#cbd1382f8ee3113ce1c42415308ab3488e641625 | https://github.com/esaueng/remus |
| remus-math | 0.1.0 | Apache-2.0 | git+https://github.com/esaueng/remus#cbd1382f8ee3113ce1c42415308ab3488e641625 | https://github.com/esaueng/remus |
| remus-offset | 0.1.0 | Apache-2.0 | git+https://github.com/esaueng/remus#cbd1382f8ee3113ce1c42415308ab3488e641625 | https://github.com/esaueng/remus |
| remus-operations | 0.1.0 | Apache-2.0 | git+https://github.com/esaueng/remus#cbd1382f8ee3113ce1c42415308ab3488e641625 | https://github.com/esaueng/remus |
| remus-sketch | 0.1.0 | Apache-2.0 | git+https://github.com/esaueng/remus#cbd1382f8ee3113ce1c42415308ab3488e641625 | https://github.com/esaueng/remus |
| remus-topology | 0.1.0 | Apache-2.0 | git+https://github.com/esaueng/remus#cbd1382f8ee3113ce1c42415308ab3488e641625 | https://github.com/esaueng/remus |
| robust | 1.2.0 | MIT OR Apache-2.0 | crates.io | https://github.com/georust/robust |
| rustversion | 1.0.23 | MIT OR Apache-2.0 | crates.io | https://github.com/dtolnay/rustversion |
| serde | 1.0.229 | MIT OR Apache-2.0 | crates.io | https://github.com/serde-rs/serde |
| serde-wasm-bindgen | 0.6.5 | MIT | crates.io | https://github.com/RReverser/serde-wasm-bindgen |
| serde_core | 1.0.229 | MIT OR Apache-2.0 | crates.io | https://github.com/serde-rs/serde |
| serde_derive | 1.0.229 | MIT OR Apache-2.0 | crates.io | https://github.com/serde-rs/serde |
| serde_json | 1.0.151 | MIT OR Apache-2.0 | crates.io | https://github.com/serde-rs/json |
| simd-adler32 | 0.3.10 | MIT | crates.io | https://github.com/mcountryman/simd-adler32 |
| slab | 0.4.12 | MIT | crates.io | https://github.com/tokio-rs/slab |
| smallvec | 1.16.0 | MIT OR Apache-2.0 | crates.io | https://github.com/servo/rust-smallvec |
| syn | 2.0.119 | MIT OR Apache-2.0 | crates.io | https://github.com/dtolnay/syn |
| syn | 3.0.4 | MIT OR Apache-2.0 | crates.io | https://github.com/dtolnay/syn |
| thiserror | 2.0.20 | MIT OR Apache-2.0 | crates.io | https://github.com/dtolnay/thiserror |
| thiserror-impl | 2.0.20 | MIT OR Apache-2.0 | crates.io | https://github.com/dtolnay/thiserror |
| typed-path | 0.12.3 | MIT OR Apache-2.0 | crates.io | https://github.com/chipsenkbeil/typed-path |
| unicode-ident | 1.0.24 | (MIT OR Apache-2.0) AND Unicode-3.0 | crates.io | https://github.com/dtolnay/unicode-ident |
| wasm-bindgen | 0.2.126 | MIT OR Apache-2.0 | crates.io | https://github.com/wasm-bindgen/wasm-bindgen |
| wasm-bindgen-macro | 0.2.126 | MIT OR Apache-2.0 | crates.io | https://github.com/wasm-bindgen/wasm-bindgen/tree/master/crates/macro |
| wasm-bindgen-macro-support | 0.2.126 | MIT OR Apache-2.0 | crates.io | https://github.com/wasm-bindgen/wasm-bindgen/tree/master/crates/macro-support |
| wasm-bindgen-shared | 0.2.126 | MIT OR Apache-2.0 | crates.io | https://github.com/wasm-bindgen/wasm-bindgen/tree/master/crates/shared |
| zip | 8.6.0 | MIT | crates.io | https://github.com/zip-rs/zip2 |
| zlib-rs | 0.6.7 | Zlib | crates.io | https://github.com/trifectatechfoundation/zlib-rs |
| zmij | 1.0.23 | MIT | crates.io | https://github.com/dtolnay/zmij |
| zopfli | 0.8.3 | Apache-2.0 | crates.io | https://github.com/zopfli-rs/zopfli |

<!-- END GENERATED RUST DEPENDENCY INVENTORY -->

To refresh and verify the inventory after changing any lockfile:

```sh
uv sync --extra dev
pnpm install --frozen-lockfile
uv run --extra dev python scripts/check_licenses.py --write-notices
uv run --extra dev python scripts/check_licenses.py
```

The checker shells out to `cargo metadata`; the Rust toolchain pinned in `rust-toolchain.toml` must
be on `PATH` or the audit fails rather than skipping the Rust ecosystem.
