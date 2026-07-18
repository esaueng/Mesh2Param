# Mesh2Param display modes QA

- Source visual truth: `/var/folders/t_/tvn84c292rzdfcbj06vltnsw0000gn/T/codex-clipboard-42cccdfc-ab9c-4a2f-9cb1-4802ff32b04b.png`
- Implementation screenshot: `/private/tmp/mesh2param-display-menu-desktop.png`
- Focused comparison: `/private/tmp/mesh2param-display-menu-comparison.png`
- Viewports: 1280 x 720 desktop and 390 x 844 mobile
- State: dark theme, validated L-bracket sample, Shaded selected, display menu open

## Full-view comparison evidence

The source establishes a dark, elevated viewport menu with grouped surface modes, a selected-state checkmark, separators, and switch options. The implementation carries that structure into Mesh2Param's existing bottom command dock: the menu opens above the display button, stays clear of the primary download action, and preserves the model, gizmo, scale bar, and product chrome.

## Focused-region comparison evidence

The side-by-side focused comparison shows the source and implementation control at readable scale. Both use a dark rounded panel, compact headings, vertically stacked modes, clear group separators, a selected Shaded row, and a blue Show edges switch. Mesh2Param intentionally adds concise descriptions and uses its existing IBM Plex type and spacing tokens. Unsupported source-app concepts such as decals and hidden-edge primitives are omitted instead of being shown as inert controls.

## Required fidelity surfaces

- Fonts and typography: IBM Plex Sans remains consistent with Mesh2Param. Heading, label, and helper-text weights establish the same hierarchy as the reference without importing an unrelated product font.
- Spacing and layout rhythm: the desktop panel is 248 px wide with 43 px rows, 8 px group padding, 12 px radius, and clear dividers. The mobile panel expands to 280 px and fits within the 390 px viewport without horizontal overflow.
- Colors and visual tokens: the panel, text, borders, hover state, selected check, and switch use existing theme variables. A light-theme portal variant carries the light token scope with it.
- Image quality and asset fidelity: all icons come from the project's Lucide icon set. Display effects are rendered from the actual GLB geometry rather than raster approximations.
- Copy and content: the menu exposes Shaded, Wireframe, X-Ray, Surface normals, Zebra, and Show edges. Descriptions clarify the actual render behavior.

## Interaction and runtime checks

- Page identity: `http://127.0.0.1:5174/`, title `Mesh2Param`.
- Interaction flow: validated sample -> Display settings -> select each mode -> viewport `data-display-mode` updates -> rendered material changes.
- Verified modes: Shaded, Wireframe, X-Ray, Surface normals, and Zebra.
- Edge option: Show edges toggles independently and remains in the open menu.
- Menu behavior: selected radio state, outside/Escape close behavior, and responsive portal placement are implemented.
- Console: no relevant errors or warnings after every mode switch, including the Zebra shader.
- Framework overlay: none.

## Comparison history

1. Initial desktop pass: menu structure and interactions matched the reference direction; all five modes rendered successfully.
2. Initial mobile pass: the dock's horizontal scroll container clipped the menu despite the DOM reporting it open. Classified P2.
3. Fix: portaled the menu to `document.body`, positioned it from the trigger on desktop and above the dock on mobile, and carried the active theme into the portal.
4. Post-fix mobile evidence: the complete 280 x 380 panel is visible at 390 x 844, stays within x=98..378, and the document remains 390 px wide. No P0, P1, or P2 issue remains.

## Findings

No actionable P0, P1, or P2 findings remain. The implementation is a product-native adaptation of the reference rather than a copy of unrelated surrounding CAD-app chrome.

final result: passed
