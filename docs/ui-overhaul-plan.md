# UI Overhaul Plan — "precision instrument, not marketing site"

Approved cross-milestone plan for the Mesh2Param web UI overhaul. Scope is
`apps/web` and `packages/ui` only. Prohibited: `engine/`, `services/`,
`packages/contracts`, API request/response shapes, job orchestration,
`apps/web/src/local/geometry/*`, and any geometry/STEP logic. Every existing
feature, flow, and behavior keeps working identically.

## Behavior contracts (load-bearing)

The Playwright suite and unit tests encode the UI's contract. These hooks must
keep working (restyle/re-layout allowed, never removed or renamed):

- `data-testid="start-screen"`, `data-testid="cad-viewport"`
  (`data-display-mode`, `data-camera-view`), `data-testid="curved-evidence"`
- `.canvas-shell` (`data-theme`), `.dock-primary`, `.canvas-progress`
  (`role="status"`), `.panel-patches > li`, `.patch-kind-*`,
  `.panel-patch-row` (`aria-selected`), `.view-settings` with
  `aria-label="View settings"` and its radios/switch names
- Accessible names: `Back to start screen`, `Try the L-bracket sample`,
  `Choose source mesh`, `Open saved project file`, `Save project`,
  `Compare`/`Result` (`aria-pressed`), `Toggle light or dark theme`,
  `Patches (N)` heading, `Select {id} for merge`, `Lock/Unlock {id}`,
  `Reclassify selected patch`, `Boundary continuity to {id}`, `Merge`/`Split`
  (+ titles), `Dismiss error` + `role="alert"` (must stay 0 in healthy flows),
  `Recent projects` list, `File name`, `3D CAD viewer`, `Debug console`

If a redesign genuinely needs a selector change, the spec is updated in the
same commit and called out in the PR.

## Gates (every milestone)

1. `pnpm --filter @mesh2param/web typecheck` (plus contracts/ui typechecks)
2. `pnpm --filter @mesh2param/web exec vitest run`
3. `pnpm --filter @mesh2param/web exec eslint src --max-warnings 0`
4. Full Playwright suite green on isolated ports
   (`MESH2PARAM_E2E_API_PORT` / `MESH2PARAM_E2E_WEB_PORT`)

Each milestone = one branch off `origin/main` (previous milestone merged in,
since PRs are never merged) = one DRAFT PR with before/after screenshots at
1440x900, 1024x768, 375x812 (dark + light), motion evidence where applicable,
and a "Plan compliance" section. Never merge, never deploy. No new heavyweight
dependencies.

## U1 — Foundation (branch `ui/u1-foundation`)

Token system, typography, base controls restyled in place with **zero layout
changes**. One tokens file (CSS custom properties): color elevations, borders,
accent ramp, semantic success/warn/error triplets, spacing, radii, type scale
(Plex Mono numerics with `tabular-nums`, Plex Sans UI), shadows, motion
durations/easings (120–240ms ease-out), focus color, z-index scale. New
`packages/ui` primitives: `Checkbox`, `Switch`, `Badge`, `Toast`. Deliverable:
dev-only `/styleguide` route (excluded from the production bundle) showing
every control state in dark and light. All scattered hex/rgba literals in
component stylesheets replaced by tokens (WebGL palette in `viewerTheme.ts`
and brand SVG artwork are the documented exceptions).

## U2 — Shell & panels (branch `ui/u2-shell-panels`)

App frame: top bar (project name, mesh stats, status chip), right command
panel reorganized into collapsible sections (File / View / Analysis / Patches
/ Convert) with persisted collapsed state, resizable panel width (drag handle,
persisted), independent scroll with the Convert section and `.dock-primary`
always reachable, and the Console as a dockable bottom drawer with severity
filtering and mono formatting.

## U3 — Viewport chrome (branch `ui/u3-viewport-chrome`)

CAD-native viewer overlays: grid floor toggle, scale bar polish, orientation
gizmo polish, hover highlight + selection outline for patches synced with the
panel (rendering only — selection logic already exists), display-mode
segmented control (Shaded/Wireframe/X-Ray/Normals/Zebra) as an on-canvas
floating toolbar that keeps the `View settings` aria contract, and job
progress as a slim viewport-top bar (same `.canvas-progress` structure)
instead of a blocking panel element.

## U4 — Responsive & states (branch `ui/u4-responsive-states`)

Deliberate layouts at desktop/tablet/mobile (panel becomes a bottom sheet on
narrow screens), the start screen redesigned to the same standard (drag-drop
affordance, recent projects as cards with thumbnails where data exists), and
designed empty/loading/error states for every region — skeletons for panels,
honest error surfaces for failed jobs with `recommendedAction` as a button.

## U5 — Polish & audit (branch `ui/u5-polish-audit`)

Full keyboard pass, focus order, aria audit, contrast audit with actual ratios
printed in the PR, reduced-motion verification, 120Hz interaction smoothness
check on the viewer (no layout thrash from panel animations), and a final
consistency sweep against the tokens.

## Definition of done (per milestone)

Gates green, screenshots attached, "Plan compliance" section in the PR body
(files touched vs allow-list, "no geometry or API changes"), and no regression
in any existing flow — upload, analyze, patch edits, merge, boundary
continuity, convert, download — demonstrated by the e2e run.
