# Real corpus baseline, 2026-09-03

Result of running the current Python engine (`mesh2param.reconstruction.reconstruct_file`,
automatic mode, units mm) on the owner-supplied STL exports that now live under
`samples/real/`. This is the Phase 0 yardstick for the reconstruction overhaul: the
number to beat is **2 of 28** parts converted, and both successes are trivial single
extrusions (a tube and a washer).

Every one of these exports is watertight, winding-consistent, and edge-manifold, so the
failures are all recognition gates, not mesh damage.

| part | result | time | rejection |
| --- | --- | ---: | --- |
| hammer-holder | rejected | 9.3s | automatic L-bracket inference requires only plane and full-cylinder patches |
| deck-cap | rejected | 0.4s | expected exactly three dominant antipodal plane directions; found 9 (coarse facets or unsupported geometry) |
| dock-wheel-cap | rejected | 0.3s | automatic L-bracket inference requires only plane and full-cylinder patches |
| dock-side-protector-cap | rejected | 1.9s | automatic L-bracket inference requires only plane and full-cylinder patches |
| ladder-cap | rejected | 1.2s | automatic L-bracket inference requires only plane and full-cylinder patches |
| lamp-cover | converted | 1.1s | |
| oil-ring | converted | 1.2s | |
| conduit-fitting | rejected | 0.9s | automatic L-bracket inference requires only plane and full-cylinder patches |
| cable-support | rejected | 0.2s | L-profile inference requires exactly two matched six-line end loops; found 0 |
| camera-support-arm | rejected | 0.7s | automatic L-bracket inference requires only plane and full-cylinder patches |
| windshield-holder-coarse | rejected | 0.8s | section supports follow a bounded linear taper |
| windshield-holder-fine | rejected | 14.7s | section supports follow a bounded linear taper |
| stand-horizontal | rejected | 3.8s | section loop count changes through the primary extent |
| thru-hull-screw | rejected | 29.1s | section loop count changes through the primary extent |
| thru-hull-hex-nut | rejected | 35.4s | section loop count changes through the primary extent |
| sail-mount | rejected | 5.6s | section loop count changes through the primary extent |
| cockpit-plug | rejected | 2.2s | section loop count changes through the primary extent |
| cooler-handle-plate | rejected | 0.9s | section loop count changes through the primary extent |
| desk-cable-clip | rejected | 1.1s | automatic L-bracket inference requires only plane and full-cylinder patches |
| handle-test | rejected | 1.3s | section loop count changes through the primary extent |
| cup-holder-bar-mount | rejected | 0.9s | section loop count changes through the primary extent |
| pole-cap | rejected | 2.1s | automatic L-bracket inference requires only plane and full-cylinder patches |
| boat-lift-cap | rejected | 0.6s | automatic L-bracket inference requires only plane and full-cylinder patches |
| solar-light-post | rejected | 1.7s | automatic L-bracket inference requires only plane and full-cylinder patches |
| laser-rail | rejected | 1.0s | automatic L-bracket inference requires only plane and full-cylinder patches |
| switch-stand | rejected | 0.2s | L-profile inference requires exactly two matched six-line end loops; found 0 |
| rear-plug-bottom | rejected | 8.5s | section loop count changes through the primary extent |
| bag-clip-150 | rejected | 2.6s | section supports follow a bounded linear taper |

Notes:

- `hammer-holder` here is the v1.3 export (`hammer-holder-v1` in the corpus); the featured
  46 mm v4 part was ingested after this run.
- The rejection strings are the engine's own diagnostics. Three gates account for almost
  everything: the L-bracket path requiring only plane and full-cylinder patches, the
  section-stack path requiring a constant loop count through the primary extent, and the
  prismatic path rejecting any taper.
- Re-run with the script in the PR description or by calling `reconstruct_file` on each
  `mesh-export.stl`; the numbers are deterministic.
