# M0 environment spike

Date: 2026-07-11  
Host: macOS 26.5.2 arm64

## Toolchain

- Node.js `22.22.2` and pnpm `11.7.0` satisfy the required versions.
- The system `python3` is `3.9.6` and is not used by Mesh2Param.
- `uv 0.11.28` was installed with Homebrew and provisioned CPython `3.12.13`.
- Git `2.50.1` is available.
- Docker `29.4.2` can reach a Colima Docker `29.2.1` daemon. Docker Compose was not installed during this spike; the delivery fallback is recorded in `docs/fallbacks.md`.
- A headless Google Chrome `150.0.7871.49` launch passed through Playwright. Project-managed Chromium installation is deferred until the Playwright workspace dependency exists.

## Verified geometry stack

The spike used these exact versions:

| Dependency | Version |
| --- | --- |
| Python | 3.12.13 |
| CadQuery | 2.8.0 |
| cadquery-ocp | 7.9.3.1.1 |
| trimesh | 4.12.2 |
| NumPy | 2.4.6 |
| SciPy | 1.18.0 |
| Shapely | 2.1.2 |
| NetworkX | 3.6.1 |

`uv pip check` reported that all 47 installed packages were compatible. Open3D was intentionally not introduced; deterministic trimesh/NumPy/SciPy fitting is the selected fallback.

## OCCT roundtrip gate

The throwaway proof constructed a 40 x 30 x 12 mm box with a centered 8 mm through-hole, exported it through CadQuery, independently reimported it with `OCP.STEPControl_Reader`, checked it with `BRepCheck_Analyzer`, reimported it through CadQuery, and tessellated the result.

```json
{
  "status": "PASS",
  "step_bytes": 20222,
  "stepcontrol_transferred_roots": 1,
  "source_solid_count": 1,
  "occt_reimport_solid_count": 1,
  "cadquery_reimport_solid_count": 1,
  "occt_shape_valid": true,
  "cadquery_solid_valid": true,
  "expected_volume_mm3": 13796.81421051076,
  "actual_volume_mm3": 13796.81421051074,
  "volume_error_mm3": 2.000888343900442e-11,
  "tessellation_vertices": 530,
  "tessellation_triangles": 520
}
```

The exported STEP SHA-256 was `972f10a54dbc1ba748d8cb9103217b6464182005b35ef0ec5e4326a64facf7a3` and its header identified Open CASCADE STEP processor 7.9.

## OpenCAE reference

OpenCAE `main` commit `a8aba0048dd21565b5b76357cfd9be62917cf6f6` was inspected from a temporary checkout. Its license is Apache-2.0. Mesh2Param may adapt generic shell, token, interaction, and accessibility patterns while retaining required attribution, but does not reuse OpenCAE branding, its trademarked logo, product copy, sample data, or support links.

The inspected shell confirmed the directive's 44 px top bar, 30 px status bar, 124/56 px workflow rail, 344 px inspector, dark/light tokens, IBM Plex typography, compact controls, keyboard safeguards, and pointer-plus-keyboard bottom drawer pattern. Mesh2Param adds the missing warning/failed workflow states, Metrics tab, stable camera behavior, full viewport modes, and native accessible tooltip controls.

## Gate result

M0 passed. A real OCCT solid survived STEP export and reimport, both OCCT validity checks passed, and the reimported solid tessellated successfully. CadQuery fallback to build123d was not needed.
