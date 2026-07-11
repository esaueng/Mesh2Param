# Mesh2Param

Mesh2Param compiles a versioned, typed CADGraph into an exact Open CASCADE B-Rep, validated STEP,
deterministic tessellated artifacts, and safe generated CadQuery source. The current M1 milestone is
the headless engine and procedural sample corpus; reconstruction, API, and web milestones follow.

## Development

Requirements: Python 3.12, Node.js 20 or newer, pnpm, and uv.

```sh
pnpm install
uv sync --extra dev
pnpm verify
pnpm mesh2param -- --help
```

Generate the ten deterministic procedural samples with `pnpm samples:generate`.

Mesh2Param reconstructs an editable, geometrically equivalent CAD model. It does not guarantee
recovery of the source designer's exact original feature history.
