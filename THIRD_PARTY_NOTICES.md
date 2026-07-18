# Third-party notices

Mesh2Param's original source is Apache-2.0. Third-party components remain under their respective
licenses; the Apache-2.0 project license does not relicense them. This notice is an engineering
inventory, not legal advice. A distributor is responsible for satisfying the licenses that apply to
the exact binaries and source it ships.

## Components requiring prominent treatment

| Component | Version in `uv.lock` | License | Use and source |
| --- | --- | --- | --- |
| Open CASCADE Technology (OCCT) | 7.9.3, embedded by `cadquery-ocp` 7.9.3.1.1 | LGPL-2.1-only with Open CASCADE exception 1.0 | Exact B-Rep construction, validation, STEP import/export, and tessellation. [OCCT source](https://github.com/Open-Cascade-SAS/OCCT/tree/V7_9_3). |
| occt-wasm | 3.6.1 | TypeScript tooling MIT OR Apache-2.0; embedded OCCT WebAssembly remains LGPL-2.1-only | Browser-local B-Rep construction, STEP import/export, validation, and tessellation. [occt-wasm source](https://github.com/andymai/occt-wasm). |
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
| Browser/runtime | React, React DOM, Three.js, R3F, Drei, Dexie, Immer, Lucide, Zustand, occt-wasm | MIT, Apache-2.0, ISC, and embedded OCCT LGPL-2.1 |
| Fonts | IBM Plex Sans and IBM Plex Mono through `@fontsource` | SIL Open Font License 1.1 |
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
| javascript | @asamuzakjp/css-color | 3.2.0 | MIT |
| javascript | @babel/code-frame | 7.29.7 | MIT |
| javascript | @babel/compat-data | 7.29.7 | MIT |
| javascript | @babel/core | 7.29.7 | MIT |
| javascript | @babel/generator | 7.29.7 | MIT |
| javascript | @babel/helper-compilation-targets | 7.29.7 | MIT |
| javascript | @babel/helper-globals | 7.29.7 | MIT |
| javascript | @babel/helper-module-imports | 7.29.7 | MIT |
| javascript | @babel/helper-module-transforms | 7.29.7 | MIT |
| javascript | @babel/helper-plugin-utils | 7.29.7 | MIT |
| javascript | @babel/helper-string-parser | 7.29.7 | MIT |
| javascript | @babel/helper-validator-identifier | 7.29.7 | MIT |
| javascript | @babel/helper-validator-option | 7.29.7 | MIT |
| javascript | @babel/helpers | 7.29.7 | MIT |
| javascript | @babel/parser | 7.29.7 | MIT |
| javascript | @babel/plugin-transform-react-jsx-self | 7.29.7 | MIT |
| javascript | @babel/plugin-transform-react-jsx-source | 7.29.7 | MIT |
| javascript | @babel/runtime | 7.29.7 | MIT |
| javascript | @babel/template | 7.29.7 | MIT |
| javascript | @babel/traverse | 7.29.7 | MIT |
| javascript | @babel/types | 7.29.7 | MIT |
| javascript | @cloudflare/kv-asset-handler | 0.5.0 | MIT OR Apache-2.0 |
| javascript | @cloudflare/unenv-preset | 2.16.1 | MIT OR Apache-2.0 |
| javascript | @cspotcode/source-map-support | 0.8.1 | MIT |
| javascript | @csstools/color-helpers | 5.1.0 | MIT-0 |
| javascript | @csstools/css-calc | 2.1.4 | MIT |
| javascript | @csstools/css-color-parser | 3.1.0 | MIT |
| javascript | @csstools/css-parser-algorithms | 3.0.5 | MIT |
| javascript | @csstools/css-tokenizer | 3.0.4 | MIT |
| javascript | @dimforge/rapier3d-compat | 0.12.0 | Apache-2.0 |
| javascript | @eslint-community/eslint-utils | 4.9.1 | MIT |
| javascript | @eslint-community/regexpp | 4.12.2 | MIT |
| javascript | @eslint/config-array | 0.21.2 | Apache-2.0 |
| javascript | @eslint/config-helpers | 0.4.2 | Apache-2.0 |
| javascript | @eslint/core | 0.17.0 | Apache-2.0 |
| javascript | @eslint/eslintrc | 3.3.5 | MIT |
| javascript | @eslint/js | 9.39.4 | MIT |
| javascript | @eslint/object-schema | 2.1.7 | Apache-2.0 |
| javascript | @eslint/plugin-kit | 0.4.1 | Apache-2.0 |
| javascript | @fontsource/ibm-plex-mono | 5.2.7 | OFL-1.1 |
| javascript | @fontsource/ibm-plex-sans | 5.2.8 | OFL-1.1 |
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
| javascript | @playwright/test | 1.61.1 | Apache-2.0 |
| javascript | @poppinss/colors | 4.1.6 | MIT |
| javascript | @poppinss/dumper | 0.6.5 | MIT |
| javascript | @poppinss/exception | 1.2.3 | MIT |
| javascript | @react-three/drei | 10.7.7 | MIT |
| javascript | @react-three/fiber | 9.6.1 | MIT |
| javascript | @rolldown/pluginutils | 1.0.0-rc.3 | MIT |
| javascript | @sindresorhus/is | 7.2.0 | MIT |
| javascript | @speed-highlight/core | 1.2.17 | CC0-1.0 |
| javascript | @testing-library/dom | 10.4.1 | MIT |
| javascript | @testing-library/jest-dom | 6.9.1 | MIT |
| javascript | @testing-library/react | 16.3.2 | MIT |
| javascript | @testing-library/user-event | 14.6.1 | MIT |
| javascript | @tweenjs/tween.js | 23.1.3 | MIT |
| javascript | @types/aria-query | 5.0.4 | MIT |
| javascript | @types/babel__core | 7.20.5 | MIT |
| javascript | @types/babel__generator | 7.27.0 | MIT |
| javascript | @types/babel__template | 7.4.4 | MIT |
| javascript | @types/babel__traverse | 7.28.0 | MIT |
| javascript | @types/chai | 5.2.3 | MIT |
| javascript | @types/deep-eql | 4.0.2 | MIT |
| javascript | @types/draco3d | 1.4.10 | MIT |
| javascript | @types/estree | 1.0.9 | MIT |
| javascript | @types/json-schema | 7.0.15 | MIT |
| javascript | @types/lodash | 4.17.24 | MIT |
| javascript | @types/node | 22.20.1 | MIT |
| javascript | @types/node | 26.1.1 | MIT |
| javascript | @types/offscreencanvas | 2019.7.3 | MIT |
| javascript | @types/react | 19.2.17 | MIT |
| javascript | @types/react-dom | 19.2.3 | MIT |
| javascript | @types/react-reconciler | 0.28.9 | MIT |
| javascript | @types/stats.js | 0.17.4 | MIT |
| javascript | @types/three | 0.180.0 | MIT |
| javascript | @types/webxr | 0.5.24 | MIT |
| javascript | @typescript-eslint/eslint-plugin | 8.63.0 | MIT |
| javascript | @typescript-eslint/parser | 8.63.0 | MIT |
| javascript | @typescript-eslint/project-service | 8.63.0 | MIT |
| javascript | @typescript-eslint/scope-manager | 8.63.0 | MIT |
| javascript | @typescript-eslint/tsconfig-utils | 8.63.0 | MIT |
| javascript | @typescript-eslint/type-utils | 8.63.0 | MIT |
| javascript | @typescript-eslint/types | 8.63.0 | MIT |
| javascript | @typescript-eslint/typescript-estree | 8.63.0 | MIT |
| javascript | @typescript-eslint/utils | 8.63.0 | MIT |
| javascript | @typescript-eslint/visitor-keys | 8.63.0 | MIT |
| javascript | @use-gesture/core | 10.3.1 | MIT |
| javascript | @use-gesture/react | 10.3.1 | MIT |
| javascript | @vitejs/plugin-react | 5.2.0 | MIT |
| javascript | @vitest/expect | 3.2.7 | MIT |
| javascript | @vitest/mocker | 3.2.7 | MIT |
| javascript | @vitest/pretty-format | 3.2.7 | MIT |
| javascript | @vitest/runner | 3.2.7 | MIT |
| javascript | @vitest/snapshot | 3.2.7 | MIT |
| javascript | @vitest/spy | 3.2.7 | MIT |
| javascript | @vitest/utils | 3.2.7 | MIT |
| javascript | @webgpu/types | 0.1.71 | BSD-3-Clause |
| javascript | acorn | 8.17.0 | MIT |
| javascript | acorn-jsx | 5.3.2 | MIT |
| javascript | agent-base | 7.1.4 | MIT |
| javascript | ajv | 6.15.0 | MIT |
| javascript | ajv | 8.20.0 | MIT |
| javascript | ajv-formats | 3.0.1 | MIT |
| javascript | ansi-regex | 5.0.1 | MIT |
| javascript | ansi-styles | 4.3.0 | MIT |
| javascript | ansi-styles | 5.2.0 | MIT |
| javascript | argparse | 2.0.1 | Python-2.0 |
| javascript | aria-query | 5.3.0 | Apache-2.0 |
| javascript | aria-query | 5.3.2 | Apache-2.0 |
| javascript | assertion-error | 2.0.1 | MIT |
| javascript | balanced-match | 1.0.2 | MIT |
| javascript | balanced-match | 4.0.4 | MIT |
| javascript | base64-js | 1.5.1 | MIT |
| javascript | baseline-browser-mapping | 2.10.42 | Apache-2.0 |
| javascript | bidi-js | 1.0.3 | MIT |
| javascript | blake3-wasm | 2.1.5 | MIT |
| javascript | brace-expansion | 1.1.16 | MIT |
| javascript | brace-expansion | 5.0.7 | MIT |
| javascript | browserslist | 4.28.5 | MIT |
| javascript | buffer | 6.0.3 | MIT |
| javascript | cac | 6.7.14 | MIT |
| javascript | callsites | 3.1.0 | MIT |
| javascript | camera-controls | 3.1.2 | MIT |
| javascript | caniuse-lite | 1.0.30001803 | CC-BY-4.0 |
| javascript | chai | 5.3.3 | MIT |
| javascript | chalk | 4.1.2 | MIT |
| javascript | check-error | 2.1.3 | MIT |
| javascript | cliui | 8.0.1 | ISC |
| javascript | color-convert | 2.0.1 | MIT |
| javascript | color-name | 1.1.4 | MIT |
| javascript | comlink | 4.4.2 | Apache-2.0 |
| javascript | concat-map | 0.0.1 | MIT |
| javascript | concurrently | 9.2.3 | MIT |
| javascript | convert-source-map | 2.0.0 | MIT |
| javascript | cookie | 1.1.1 | MIT |
| javascript | cross-env | 7.0.3 | MIT |
| javascript | cross-spawn | 7.0.6 | MIT |
| javascript | css.escape | 1.5.1 | MIT |
| javascript | cssstyle | 4.6.0 | MIT |
| javascript | csstype | 3.2.3 | MIT |
| javascript | data-urls | 5.0.0 | MIT |
| javascript | debug | 4.4.3 | MIT |
| javascript | decimal.js | 10.6.0 | MIT |
| javascript | deep-eql | 5.0.2 | MIT |
| javascript | deep-is | 0.1.4 | MIT |
| javascript | dequal | 2.0.3 | MIT |
| javascript | detect-gpu | 5.0.70 | MIT |
| javascript | detect-libc | 2.1.2 | Apache-2.0 |
| javascript | dexie | 4.4.4 | Apache-2.0 |
| javascript | dom-accessibility-api | 0.5.16 | MIT |
| javascript | dom-accessibility-api | 0.6.3 | MIT |
| javascript | draco3d | 1.5.7 | Apache-2.0 |
| javascript | electron-to-chromium | 1.5.389 | ISC |
| javascript | emoji-regex | 8.0.0 | MIT |
| javascript | entities | 6.0.1 | BSD-2-Clause |
| javascript | error-stack-parser-es | 1.0.5 | MIT |
| javascript | es-module-lexer | 1.7.0 | MIT |
| javascript | esbuild | 0.28.1 | MIT |
| javascript | escalade | 3.2.0 | MIT |
| javascript | escape-string-regexp | 4.0.0 | MIT |
| javascript | eslint | 9.39.4 | MIT |
| javascript | eslint-plugin-react-hooks | 6.1.1 | MIT |
| javascript | eslint-scope | 8.4.0 | BSD-2-Clause |
| javascript | eslint-visitor-keys | 3.4.3 | Apache-2.0 |
| javascript | eslint-visitor-keys | 4.2.1 | Apache-2.0 |
| javascript | eslint-visitor-keys | 5.0.1 | Apache-2.0 |
| javascript | espree | 10.4.0 | BSD-2-Clause |
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
| javascript | fast-uri | 3.1.3 | BSD-3-Clause |
| javascript | fdir | 6.5.0 | MIT |
| javascript | fflate | 0.6.10 | MIT |
| javascript | fflate | 0.8.3 | MIT |
| javascript | file-entry-cache | 8.0.0 | MIT |
| javascript | find-up | 5.0.0 | MIT |
| javascript | flat-cache | 4.0.1 | MIT |
| javascript | flatted | 3.4.2 | ISC |
| javascript | gensync | 1.0.0-beta.2 | MIT |
| javascript | get-caller-file | 2.0.5 | ISC |
| javascript | glob-parent | 6.0.2 | ISC |
| javascript | globals | 14.0.0 | MIT |
| javascript | glsl-noise | 0.0.0 | MIT |
| javascript | has-flag | 4.0.0 | MIT |
| javascript | hls.js | 1.6.16 | Apache-2.0 |
| javascript | html-encoding-sniffer | 4.0.0 | MIT |
| javascript | http-proxy-agent | 7.0.2 | MIT |
| javascript | https-proxy-agent | 7.0.6 | MIT |
| javascript | iconv-lite | 0.6.3 | MIT |
| javascript | ieee754 | 1.2.1 | BSD-3-Clause |
| javascript | ignore | 5.3.2 | MIT |
| javascript | ignore | 7.0.5 | MIT |
| javascript | immediate | 3.0.6 | MIT |
| javascript | immer | 10.2.0 | MIT |
| javascript | import-fresh | 3.3.1 | MIT |
| javascript | imurmurhash | 0.1.4 | MIT |
| javascript | indent-string | 4.0.0 | MIT |
| javascript | is-extglob | 2.1.1 | MIT |
| javascript | is-fullwidth-code-point | 3.0.0 | MIT |
| javascript | is-glob | 4.0.3 | MIT |
| javascript | is-potential-custom-element-name | 1.0.1 | MIT |
| javascript | is-promise | 2.2.2 | MIT |
| javascript | isexe | 2.0.0 | ISC |
| javascript | its-fine | 2.0.0 | MIT |
| javascript | js-tokens | 4.0.0 | MIT |
| javascript | js-tokens | 9.0.1 | MIT |
| javascript | js-yaml | 4.3.0 | MIT |
| javascript | jsdom | 26.1.0 | MIT |
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
| javascript | locate-path | 6.0.0 | MIT |
| javascript | lodash | 4.18.1 | MIT |
| javascript | lodash.merge | 4.6.2 | MIT |
| javascript | loupe | 3.2.1 | MIT |
| javascript | lru-cache | 10.4.3 | ISC |
| javascript | lru-cache | 5.1.1 | ISC |
| javascript | lucide-react | 0.544.0 | ISC |
| javascript | lz-string | 1.5.0 | MIT |
| javascript | maath | 0.10.8 | MIT |
| javascript | magic-string | 0.30.21 | MIT |
| javascript | meshline | 3.3.1 | MIT |
| javascript | meshoptimizer | 0.22.0 | MIT |
| javascript | min-indent | 1.0.1 | MIT |
| javascript | miniflare | 4.20260708.1 | MIT |
| javascript | minimatch | 10.2.5 | BlueOak-1.0.0 |
| javascript | minimatch | 3.1.5 | ISC |
| javascript | minimist | 1.2.8 | MIT |
| javascript | ms | 2.1.3 | MIT |
| javascript | nanoid | 3.3.15 | MIT |
| javascript | natural-compare | 1.4.0 | MIT |
| javascript | node-releases | 2.0.51 | MIT |
| javascript | nwsapi | 2.2.24 | MIT |
| javascript | occt-wasm | 3.6.1 | MIT OR Apache-2.0 |
| javascript | optionator | 0.9.4 | MIT |
| javascript | p-limit | 3.1.0 | MIT |
| javascript | p-locate | 5.0.0 | MIT |
| javascript | parent-module | 1.0.1 | MIT |
| javascript | parse5 | 7.3.0 | MIT |
| javascript | path-exists | 4.0.0 | MIT |
| javascript | path-key | 3.1.1 | MIT |
| javascript | path-to-regexp | 6.3.0 | MIT |
| javascript | pathe | 2.0.3 | MIT |
| javascript | pathval | 2.0.1 | MIT |
| javascript | picocolors | 1.1.1 | ISC |
| javascript | picomatch | 4.0.5 | MIT |
| javascript | playwright | 1.61.1 | Apache-2.0 |
| javascript | playwright-core | 1.61.1 | Apache-2.0 |
| javascript | postcss | 8.5.16 | MIT |
| javascript | potpack | 1.0.2 | ISC |
| javascript | prelude-ls | 1.2.1 | MIT |
| javascript | prettier | 3.9.5 | MIT |
| javascript | pretty-format | 27.5.1 | MIT |
| javascript | promise-worker-transferable | 1.0.4 | Apache-2.0 |
| javascript | punycode | 2.3.1 | MIT |
| javascript | react | 19.2.7 | MIT |
| javascript | react-dom | 19.2.7 | MIT |
| javascript | react-is | 17.0.2 | MIT |
| javascript | react-refresh | 0.18.0 | MIT |
| javascript | react-use-measure | 2.1.7 | MIT |
| javascript | redent | 3.0.0 | MIT |
| javascript | require-directory | 2.1.1 | MIT |
| javascript | require-from-string | 2.0.2 | MIT |
| javascript | resolve-from | 4.0.0 | MIT |
| javascript | rollup | 4.62.2 | MIT |
| javascript | rrweb-cssom | 0.8.0 | MIT |
| javascript | rxjs | 7.8.2 | Apache-2.0 |
| javascript | safer-buffer | 2.1.2 | MIT |
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
| javascript | std-env | 3.10.0 | MIT |
| javascript | string-width | 4.2.3 | MIT |
| javascript | strip-ansi | 6.0.1 | MIT |
| javascript | strip-indent | 3.0.0 | MIT |
| javascript | strip-json-comments | 3.1.1 | MIT |
| javascript | strip-literal | 3.1.0 | MIT |
| javascript | supports-color | 10.2.2 | MIT |
| javascript | supports-color | 7.2.0 | MIT |
| javascript | supports-color | 8.1.1 | MIT |
| javascript | suspend-react | 0.1.3 | MIT |
| javascript | symbol-tree | 3.2.4 | MIT |
| javascript | three | 0.180.0 | MIT |
| javascript | three-mesh-bvh | 0.8.3 | MIT |
| javascript | three-stdlib | 2.36.1 | MIT |
| javascript | tinybench | 2.9.0 | MIT |
| javascript | tinyexec | 0.3.2 | MIT |
| javascript | tinyglobby | 0.2.17 | MIT |
| javascript | tinypool | 1.1.1 | MIT |
| javascript | tinyrainbow | 2.0.0 | MIT |
| javascript | tinyspy | 4.0.4 | MIT |
| javascript | tldts | 6.1.86 | MIT |
| javascript | tldts-core | 6.1.86 | MIT |
| javascript | tough-cookie | 5.1.2 | BSD-3-Clause |
| javascript | tr46 | 5.1.1 | MIT |
| javascript | tree-kill | 1.2.2 | MIT |
| javascript | troika-three-text | 0.52.4 | MIT |
| javascript | troika-three-utils | 0.52.4 | MIT |
| javascript | troika-worker-utils | 0.52.0 | MIT |
| javascript | ts-api-utils | 2.5.0 | MIT |
| javascript | tslib | 2.8.1 | 0BSD |
| javascript | tunnel-rat | 0.1.2 | MIT |
| javascript | type-check | 0.4.0 | MIT |
| javascript | typescript | 5.9.3 | Apache-2.0 |
| javascript | typescript-eslint | 8.63.0 | MIT |
| javascript | undici | 7.28.0 | MIT |
| javascript | undici-types | 6.21.0 | MIT |
| javascript | undici-types | 8.3.0 | MIT |
| javascript | unenv | 2.0.0-rc.24 | MIT |
| javascript | update-browserslist-db | 1.2.3 | MIT |
| javascript | uri-js | 4.4.1 | BSD-2-Clause |
| javascript | use-sync-external-store | 1.6.0 | MIT |
| javascript | utility-types | 3.11.0 | MIT |
| javascript | vite | 7.3.6 | MIT |
| javascript | vite-node | 3.2.4 | MIT |
| javascript | vitest | 3.2.7 | MIT |
| javascript | w3c-xmlserializer | 5.0.0 | MIT |
| javascript | webgl-constants | 1.1.1 | MIT |
| javascript | webgl-sdf-generator | 1.1.1 | MIT |
| javascript | webidl-conversions | 7.0.0 | BSD-2-Clause |
| javascript | whatwg-encoding | 3.1.1 | MIT |
| javascript | whatwg-mimetype | 4.0.0 | MIT |
| javascript | whatwg-url | 14.2.0 | MIT |
| javascript | which | 2.0.2 | ISC |
| javascript | why-is-node-running | 2.3.0 | MIT |
| javascript | word-wrap | 1.2.5 | MIT |
| javascript | workerd | 1.20260708.1 | Apache-2.0 |
| javascript | wrangler | 4.110.0 | MIT OR Apache-2.0 |
| javascript | wrap-ansi | 7.0.0 | MIT |
| javascript | ws | 8.21.0 | MIT |
| javascript | xml-name-validator | 5.0.0 | Apache-2.0 |
| javascript | xmlchars | 2.2.0 | MIT |
| javascript | y18n | 5.0.8 | ISC |
| javascript | yallist | 3.1.1 | ISC |
| javascript | yargs | 17.7.2 | MIT |
| javascript | yargs-parser | 21.1.1 | ISC |
| javascript | yocto-queue | 0.1.0 | MIT |
| javascript | youch | 4.1.0-beta.10 | MIT |
| javascript | youch-core | 0.3.3 | MIT |
| javascript | zod | 4.4.3 | MIT |
| javascript | zod-validation-error | 4.0.2 | MIT |
| javascript | zustand | 4.5.7 | MIT |
| javascript | zustand | 5.0.14 | MIT |
| python | PyYAML | 6.0.3 | MIT |
| python | Pygments | 2.20.0 | BSD-2-Clause |
| python | SQLAlchemy | 2.0.41 | MIT |
| python | aiohappyeyeballs | 2.7.1 | PSF-2.0 |
| python | aiohttp | 3.14.1 | Apache-2.0 AND MIT |
| python | aiosignal | 1.4.0 | Apache-2.0 |
| python | annotated-doc | 0.0.4 | MIT |
| python | annotated-types | 0.7.0 | MIT |
| python | anyio | 4.14.1 | MIT |
| python | arrow | 1.4.0 | Apache-2.0 |
| python | attrs | 26.1.0 | MIT |
| python | cadquery | 2.8.0 | Apache-2.0 |
| python | cadquery-ocp | 7.9.3.1.1 | Apache-2.0 AND LGPL-2.1-only WITH OCCT-exception-1.0 |
| python | cadquery-ocp-proxy | 7.9.3.1.1 | Apache-2.0 |
| python | casadi | 3.7.2 | LGPL-3.0-or-later |
| python | certifi | 2026.6.17 | MPL-2.0 |
| python | click | 8.4.2 | BSD-3-Clause |
| python | contourpy | 1.3.3 | BSD-3-Clause |
| python | cycler | 0.12.1 | BSD-3-Clause |
| python | ezdxf | 1.4.4 | MIT |
| python | fastapi | 0.139.0 | MIT |
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
| python | mypy | 1.20.2 | MIT |
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
| python | pydantic-settings | 2.10.1 | MIT |
| python | pydantic_core | 2.46.4 | MIT |
| python | pyparsing | 3.3.2 | MIT |
| python | pytest | 8.4.2 | MIT |
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
| python | uvicorn | 0.35.0 | BSD-3-Clause |
| python | vtk | 9.6.2 | BSD-3-Clause |
| python | webcolors | 25.10.0 | BSD-3-Clause |
| python | wslink | 2.5.7 | BSD-3-Clause |
| python | yarl | 1.24.2 | Apache-2.0 |

<!-- END GENERATED DEPENDENCY INVENTORY -->

To refresh and verify the inventory after changing either lockfile:

```sh
uv sync --extra dev
pnpm install --frozen-lockfile
uv run --extra dev python scripts/check_licenses.py --write-notices
uv run --extra dev python scripts/check_licenses.py
```
