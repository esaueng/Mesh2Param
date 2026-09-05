import { useGLTF } from "@react-three/drei";
import type { ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { WireframeGeometry2 } from "three/examples/jsm/lines/WireframeGeometry2.js";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { GLTF } from "three-stdlib";
import type { ViewerShading } from "../state/types";
import { profileSceneBuild } from "./buildProfile";
import { surfaceColor, viewerPalette, type ViewerTheme } from "./viewerTheme";

export interface SelectionRange {
  triangleStart: number;
  triangleEndExclusive: number;
  patchId: string;
  semanticIds: string[];
}

export function patchForFace(ranges: SelectionRange[], faceIndex: number): string | null {
  let low = 0;
  let high = ranges.length - 1;
  while (low <= high) {
    const mid = (low + high) >> 1;
    const range = ranges[mid];
    if (range === undefined) return null;
    if (faceIndex < range.triangleStart) high = mid - 1;
    else if (faceIndex >= range.triangleEndExclusive) low = mid + 1;
    else return range.patchId;
  }
  return null;
}

export function selectedTriangleRanges(ranges: SelectionRange[], patchId: string | null): SelectionRange[] {
  return patchId === null ? [] : ranges.filter((range) => range.patchId === patchId);
}

/**
 * Boundary of a patch as line segments: every triangle edge of the selected
 * ranges that is not shared by another triangle of the same ranges. Positions
 * are compared by rounded coordinates so meshes with duplicated vertices
 * still close their loops. Returns flat xyz pairs in the object's local space.
 */
export function patchOutlinePositions(
  geometry: THREE.BufferGeometry,
  ranges: SelectionRange[],
  patchId: string | null,
  triangleOffset = 0,
): number[] {
  const selected = selectedTriangleRanges(ranges, patchId);
  const position = geometry.getAttribute("position");
  if (selected.length === 0 || !isReadableBufferAttribute(position)) return [];
  const index = geometry.index;
  const triangleCount = index === null ? Math.floor(position.count / 3) : Math.floor(index.count / 3);
  const key = (vertex: number) => `${position.getX(vertex).toFixed(5)},${position.getY(vertex).toFixed(5)},${position.getZ(vertex).toFixed(5)}`;
  const edges = new Map<string, { count: number; a: number; b: number }>();
  for (const range of selected) {
    const start = Math.max(0, range.triangleStart - triangleOffset);
    const end = Math.min(triangleCount, range.triangleEndExclusive - triangleOffset);
    for (let triangle = start; triangle < end; triangle += 1) {
      const corners = [0, 1, 2].map((corner) => index?.getX(triangle * 3 + corner) ?? triangle * 3 + corner);
      const keys = corners.map(key);
      // A hidden (degenerate) triangle contributes no boundary.
      if (keys[0] === keys[1] || keys[1] === keys[2] || keys[0] === keys[2]) continue;
      for (let side = 0; side < 3; side += 1) {
        const a = side;
        const b = (side + 1) % 3;
        const edgeKey = keys[a]! < keys[b]! ? `${keys[a]}|${keys[b]}` : `${keys[b]}|${keys[a]}`;
        const entry = edges.get(edgeKey);
        if (entry === undefined) edges.set(edgeKey, { count: 1, a: corners[a]!, b: corners[b]! });
        else entry.count += 1;
      }
    }
  }
  const out: number[] = [];
  for (const entry of edges.values()) {
    if (entry.count !== 1) continue;
    out.push(
      position.getX(entry.a), position.getY(entry.a), position.getZ(entry.a),
      position.getX(entry.b), position.getY(entry.b), position.getZ(entry.b),
    );
  }
  return out;
}

export function usesAnalyticResultShading(mode: string): boolean {
  return mode === "reconstructed";
}

export type EdgeOverlayKind = "none" | "triangles" | "creases" | "analytic";
export const MAX_TRIANGLE_EDGE_OVERLAY = 20_000;

export function usesCreasedSurfaceNormals(
  mode: string,
  comparisonGhost: boolean,
  facetedProxy = false,
): boolean {
  return !facetedProxy && (usesAnalyticResultShading(mode) || comparisonGhost);
}

export function edgeOverlayKind(
  mode: string,
  wireframe: boolean,
  edges: boolean,
  comparisonGhost: boolean,
  triangleCount = 0,
  facetedProxy = false,
  analyticEdges = false,
): EdgeOverlayKind {
  if (!edges || wireframe || comparisonGhost) return "none";
  // Dense meshes stay on the lightweight path; a faceted proxy is only gated on that count,
  // not suppressed outright, and draws creases like any other result: its facet boundaries
  // are exactly the edges above the threshold, and its coplanar tessellation is not.
  if (triangleCount > MAX_TRIANGLE_EDGE_OVERLAY && (mode === "source" || facetedProxy)) return "none";
  if (mode === "reconstructed" && !facetedProxy && analyticEdges) return "analytic";
  return mode === "reconstructed" ? "creases" : "triangles";
}

export function displayMaterialProperties(shading: ViewerShading, opacity: number) {
  const displayedOpacity = shading === "xray" ? Math.min(opacity, 0.28) : opacity;
  return {
    displayedOpacity,
    transparent: displayedOpacity < 1,
    depthWrite: shading !== "xray" && displayedOpacity > 0.55,
    wireframe: shading === "wireframe",
  };
}

interface ArtifactLayerProps {
  url: string;
  mode: string;
  opacity: number;
  shading: ViewerShading;
  edges: boolean;
  comparisonGhost: boolean;
  facetedProxy: boolean;
  theme: ViewerTheme;
  selectionRanges: SelectionRange[];
  hiddenPatchIds: readonly string[];
  selectedPatchId: string | null;
  hoveredPatchId?: string | null;
  sectionPlane: THREE.Plane | null;
  measurementEnabled: boolean;
  onBounds(box: THREE.Box3): void;
  onSelectPatch?(id: string): void;
  onHoverPatch?(id: string | null): void;
  onMeasurePoint?(point: THREE.Vector3): void;
}

export function ArtifactLayer({
  url,
  mode,
  opacity,
  shading,
  edges,
  comparisonGhost,
  facetedProxy,
  theme,
  selectionRanges,
  hiddenPatchIds,
  selectedPatchId,
  hoveredPatchId = null,
  sectionPlane,
  measurementEnabled,
  onBounds,
  onSelectPatch,
  onHoverPatch,
  onMeasurePoint,
}: ArtifactLayerProps) {
  // The cache entry for `url` outlives this component: layers remount on every
  // display-mode, opacity, shading, and theme change, and the SHA-256 addressed
  // bytes behind the URL cannot have changed in between. CadViewport owns
  // eviction; see viewer/gltfCache.ts. Only the resources cloned below are
  // disposed here.
  const gltf = useGLTF(url) as GLTF;
  const palette = viewerPalette(theme);
  const object = useMemo(() => profileSceneBuild(() => {
    const clone = gltf.scene.clone(true);
    if (mode === "patches") hidePatchTriangles(clone, selectionRanges, hiddenPatchIds);
    const triangleCount = objectTriangleCount(clone);
    const analyticEdges = hasAnalyticEdgeGeometry(clone);
    const smoothSurface = usesCreasedSurfaceNormals(mode, comparisonGhost, facetedProxy);
    const overlayKind = edgeOverlayKind(
      mode,
      shading === "wireframe",
      edges,
      comparisonGhost,
      triangleCount,
      facetedProxy,
      analyticEdges,
    );
    clone.traverse((child) => {
      if (child instanceof THREE.LineSegments) {
        child.visible = false;
        child.material = Array.isArray(child.material)
          ? child.material.map((material) => material.clone())
          : child.material.clone();
        return;
      }
      if (!(child instanceof THREE.Mesh)) return;
      if (smoothSurface && child.geometry instanceof THREE.BufferGeometry) {
        child.geometry = toCreasedNormals(child.geometry, Math.PI / 6);
        child.geometry.userData.mesh2paramOwned = true;
      }
      const source = Array.isArray(child.material) ? child.material[0] : child.material;
      const display = displayMaterialProperties(shading, opacity);
      const material = createDisplayMaterial(source, shading, display.displayedOpacity, !smoothSurface, palette);
      material.transparent = display.transparent;
      material.opacity = display.displayedOpacity;
      material.depthWrite = display.depthWrite;
      if ("wireframe" in material) material.wireframe = display.wireframe;
      material.polygonOffset = overlayKind !== "none";
      material.polygonOffsetFactor = 1;
      material.polygonOffsetUnits = 1;
      material.side = comparisonGhost ? THREE.FrontSide : THREE.DoubleSide;
      material.clippingPlanes = sectionPlane === null ? null : [sectionPlane];
      if (material instanceof THREE.MeshStandardMaterial) {
        material.flatShading = !smoothSurface;
        material.roughness = 0.72;
        material.metalness = 0.04;
        const color = surfaceColor(mode, palette);
        if (color !== null) material.color = new THREE.Color(color);
        material.needsUpdate = true;
      }
      if (mode === "patches") material.vertexColors = false;
      child.material = material;
    });
    if (overlayKind !== "none") {
      addShadedEdgeOverlays(clone, palette, displayMaterialProperties(shading, opacity).displayedOpacity, sectionPlane, overlayKind);
    }
    return clone;
  }), [
    comparisonGhost,
    edges,
    facetedProxy,
    gltf.scene,
    hiddenPatchIds,
    mode,
    opacity,
    palette,
    sectionPlane,
    selectionRanges,
    shading,
  ]);

  const highlight = useMemo(
    () => mode === "patches" ? makePatchHighlight(object, selectionRanges, selectedPatchId, palette) : null,
    [mode, object, palette, selectedPatchId, selectionRanges],
  );
  // The hover wash is a lighter, non-emissive twin of the selection highlight;
  // it is never drawn for the patch that is already selected.
  const hoverHighlight = useMemo(
    () => mode === "patches" && hoveredPatchId !== null && hoveredPatchId !== selectedPatchId
      ? makePatchHighlight(object, selectionRanges, hoveredPatchId, palette, "hover")
      : null,
    [hoveredPatchId, mode, object, palette, selectedPatchId, selectionRanges],
  );
  const outline = useMemo(
    () => mode === "patches" ? makePatchOutline(object, selectionRanges, selectedPatchId, palette, sectionPlane) : null,
    [mode, object, palette, sectionPlane, selectedPatchId, selectionRanges],
  );

  useEffect(() => {
    const box = new THREE.Box3().setFromObject(object);
    if (!box.isEmpty()) onBounds(box);
    return () => {
      object.traverse((child) => {
        if (!(child instanceof THREE.Mesh || child instanceof THREE.LineSegments)) return;
        if (child.geometry.userData.mesh2paramOwned === true) child.geometry.dispose();
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        for (const material of materials) material.dispose();
      });
    };
  }, [object, onBounds]);

  useEffect(() => () => disposeObject(highlight), [highlight]);
  useEffect(() => () => disposeObject(hoverHighlight), [hoverHighlight]);
  useEffect(() => () => disposeObject(outline), [outline]);
  const lastHover = useRef<string | null>(null);
  useEffect(() => () => {
    if (lastHover.current !== null) onHoverPatch?.(null);
  }, [onHoverPatch]);

  function hover(event: ThreeEvent<PointerEvent>) {
    if (onHoverPatch === undefined || measurementEnabled) return;
    const id = typeof event.faceIndex === "number" ? patchForFace(selectionRanges, event.faceIndex) : null;
    if (id === lastHover.current) return;
    lastHover.current = id;
    onHoverPatch(id);
  }

  function leave() {
    if (onHoverPatch === undefined || lastHover.current === null) return;
    lastHover.current = null;
    onHoverPatch(null);
  }

  function select(event: ThreeEvent<MouseEvent>) {
    if (measurementEnabled && onMeasurePoint !== undefined) {
      event.stopPropagation();
      onMeasurePoint(event.point.clone());
      return;
    }
    if (onSelectPatch === undefined || typeof event.faceIndex !== "number") return;
    const id = patchForFace(selectionRanges, event.faceIndex);
    if (id !== null) {
      event.stopPropagation();
      onSelectPatch(id);
    }
  }

  return (
    <group>
      <primitive
        object={object}
        onClick={select}
        {...(onHoverPatch !== undefined && mode === "patches" ? { onPointerMove: hover, onPointerOut: leave } : {})}
      />
      {hoverHighlight === null ? null : <primitive object={hoverHighlight} data-testid="hovered-patch-highlight" />}
      {highlight === null ? null : <primitive object={highlight} data-testid="selected-patch-highlight" />}
      {outline === null ? null : <primitive object={outline} data-testid="selected-patch-outline" />}
    </group>
  );
}

function createDisplayMaterial(
  source: THREE.Material | undefined,
  shading: ViewerShading,
  opacity: number,
  flatShading: boolean,
  palette: ReturnType<typeof viewerPalette>,
): THREE.Material {
  if (shading === "normals") {
    return new THREE.MeshNormalMaterial({ flatShading, opacity, side: THREE.DoubleSide });
  }
  if (shading === "zebra") {
    return new THREE.ShaderMaterial({
      uniforms: {
        opacity: { value: opacity },
        darkColor: { value: new THREE.Color(palette.background) },
        lightColor: { value: new THREE.Color(palette.surfaces.reconstructed) },
      },
      vertexShader: `
        varying vec3 vViewNormal;
        varying vec3 vViewPosition;
        #include <clipping_planes_pars_vertex>
        void main() {
          vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
          vViewPosition = viewPosition.xyz;
          vViewNormal = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * viewPosition;
          #include <clipping_planes_vertex>
        }
      `,
      fragmentShader: `
        uniform float opacity;
        uniform vec3 darkColor;
        uniform vec3 lightColor;
        varying vec3 vViewNormal;
        varying vec3 vViewPosition;
        #include <clipping_planes_pars_fragment>
        void main() {
          #include <clipping_planes_fragment>
          vec3 viewDirection = normalize(-vViewPosition);
          vec3 reflected = reflect(-viewDirection, normalize(vViewNormal));
          float wave = 0.5 + 0.5 * sin((reflected.x + reflected.y * 0.32) * 84.0);
          float stripe = smoothstep(0.44, 0.56, wave);
          gl_FragColor = vec4(mix(darkColor, lightColor, stripe), opacity);
        }
      `,
      side: THREE.DoubleSide,
      clipping: true,
    });
  }
  return (source ?? new THREE.MeshStandardMaterial()).clone();
}

function objectTriangleCount(object: THREE.Object3D): number {
  let total = 0;
  object.traverse((child) => {
    if (!(child instanceof THREE.Mesh) || !(child.geometry instanceof THREE.BufferGeometry)) return;
    const position = child.geometry.getAttribute("position");
    const index = child.geometry.index;
    total += Math.floor((index?.count ?? position?.count ?? 0) / 3);
  });
  return total;
}

/**
 * Degenerate hidden patch triangles in a display-only geometry clone.
 *
 * Keeping the original index length preserves the selection map's face indices,
 * while zero-area triangles are neither rendered nor raycast. Edge overlays are
 * built from this filtered clone, so hidden surfaces cannot leave selectable or
 * visible wireframe remnants. The cached GLTF and every export remain untouched.
 */
export function hidePatchTriangles(
  object: THREE.Object3D,
  ranges: SelectionRange[],
  hiddenPatchIds: readonly string[],
): number {
  if (ranges.length === 0 || hiddenPatchIds.length === 0) return 0;
  const hiddenIds = new Set(hiddenPatchIds);
  let triangleOffset = 0;
  let hiddenTriangleCount = 0;

  object.traverse((child) => {
    if (!(child instanceof THREE.Mesh) || !(child.geometry instanceof THREE.BufferGeometry)) return;
    const position = child.geometry.getAttribute("position");
    if (!(position instanceof THREE.BufferAttribute)) return;
    const sourceIndex = child.geometry.getIndex();
    const triangleCount = Math.floor((sourceIndex?.count ?? position.count) / 3);
    const localHidden: number[] = [];
    for (const range of ranges) {
      if (!hiddenIds.has(range.patchId)) continue;
      const start = Math.max(0, range.triangleStart - triangleOffset);
      const end = Math.min(triangleCount, range.triangleEndExclusive - triangleOffset);
      for (let triangle = start; triangle < end; triangle += 1) localHidden.push(triangle);
    }
    triangleOffset += triangleCount;
    if (localHidden.length === 0) return;

    const geometry = child.geometry.clone();
    if (geometry.getIndex() === null) {
      const IndexArray = position.count > 65_535 ? Uint32Array : Uint16Array;
      const indices = new IndexArray(position.count);
      for (let index = 0; index < indices.length; index += 1) indices[index] = index;
      geometry.setIndex(new THREE.BufferAttribute(indices, 1));
    }
    const index = geometry.getIndex();
    if (index === null) return;
    for (const triangle of localHidden) {
      const first = index.getX(triangle * 3);
      index.setX(triangle * 3 + 1, first);
      index.setX(triangle * 3 + 2, first);
    }
    index.needsUpdate = true;
    geometry.userData.mesh2paramOwned = true;
    child.geometry = geometry;
    hiddenTriangleCount += localHidden.length;
  });
  return hiddenTriangleCount;
}

function hasAnalyticEdgeGeometry(object: THREE.Object3D): boolean {
  let found = false;
  object.traverse((child) => {
    if (child instanceof THREE.LineSegments) found = true;
  });
  return found;
}

function isReadableBufferAttribute(
  value: THREE.BufferAttribute | THREE.InterleavedBufferAttribute | undefined,
): value is THREE.BufferAttribute | THREE.InterleavedBufferAttribute {
  return value instanceof THREE.BufferAttribute || value instanceof THREE.InterleavedBufferAttribute;
}

export function lineSegmentPositions(geometry: THREE.BufferGeometry): number[] {
  const position = geometry.getAttribute("position");
  if (!isReadableBufferAttribute(position)) return [];
  const index = geometry.index;
  const count = index?.count ?? position.count;
  const positions: number[] = [];
  for (let item = 0; item + 1 < count; item += 2) {
    for (const offset of [0, 1]) {
      const vertex = index?.getX(item + offset) ?? item + offset;
      positions.push(position.getX(vertex), position.getY(vertex), position.getZ(vertex));
    }
  }
  return positions;
}

/**
 * Add dark CAD edges over the solid surface.
 *
 * Exact result GLBs carry adaptively sampled B-Rep curves. Source/faceted
 * artifacts retain the mesh-derived paths. All draw fat lines rather than GL
 * lines: WebGL caps ordinary line widths at one device pixel, while
 * LineSegments2 keeps its resolution uniform synced to the viewport.
 */
function addShadedEdgeOverlays(
  object: THREE.Object3D,
  palette: ReturnType<typeof viewerPalette>,
  opacity: number,
  sectionPlane: THREE.Plane | null,
  kind: Exclude<EdgeOverlayKind, "none">,
) {
  const edgeMaterial = () => new LineMaterial({
    color: new THREE.Color(palette.edge).getHex(),
    linewidth: palette.edgeWidth,
    transparent: true,
    opacity: palette.edgeOpacity * opacity,
    depthWrite: false,
    clippingPlanes: sectionPlane === null ? null : [sectionPlane],
  });
  if (kind === "analytic") {
    const lines: THREE.LineSegments[] = [];
    let segmentCount = 0;
    object.traverse((child) => {
      if (child instanceof THREE.LineSegments) lines.push(child);
    });
    for (const line of lines) {
      const positions = lineSegmentPositions(line.geometry);
      if (positions.length === 0 || line.parent === null) continue;
      segmentCount += positions.length / 6;
      const geometry = new LineSegmentsGeometry();
      geometry.setPositions(positions);
      geometry.userData.mesh2paramOwned = true;
      const overlay = new LineSegments2(geometry, edgeMaterial());
      overlay.name = "mesh2param-analytic-edges";
      overlay.position.copy(line.position);
      overlay.quaternion.copy(line.quaternion);
      overlay.scale.copy(line.scale);
      overlay.renderOrder = 10;
      overlay.userData.mesh2paramEdgeOverlay = true;
      overlay.raycast = () => {};
      line.parent.add(overlay);
    }
    performance.mark("mesh2param:analytic-edge-overlay", {
      detail: { segmentCount },
    });
    return;
  }

  const meshes: THREE.Mesh[] = [];
  object.traverse((child) => {
    if (child instanceof THREE.Mesh && child.geometry instanceof THREE.BufferGeometry) meshes.push(child);
  });
  for (const mesh of meshes) {
    const geometry = kind === "creases"
      ? new LineSegmentsGeometry().fromEdgesGeometry(new THREE.EdgesGeometry(mesh.geometry, 30))
      : new WireframeGeometry2(mesh.geometry);
    // A result whose tessellation is smooth everywhere yields no creases above the threshold.
    if ((geometry.attributes.instanceStart?.count ?? 0) === 0) {
      geometry.dispose();
      continue;
    }
    geometry.userData.mesh2paramOwned = true;
    const overlay = new LineSegments2(geometry, edgeMaterial());
    overlay.name = kind === "creases" ? "mesh2param-feature-edges" : "mesh2param-shaded-edges";
    overlay.renderOrder = 10;
    overlay.userData.mesh2paramEdgeOverlay = true;
    // Patch picking reads faceIndex off the surface; a hit on the overlay has none.
    overlay.raycast = () => {};
    mesh.add(overlay);
  }
}

function disposeObject(item: THREE.Object3D | null) {
  if (item === null || !(item instanceof THREE.Mesh)) return;
  item.geometry.dispose();
  const material = item.material;
  if (Array.isArray(material)) material.forEach((entry) => entry.dispose());
  else material.dispose();
}

/** Fat-line boundary of the selected patch, drawn through the surface. */
function makePatchOutline(
  object: THREE.Object3D,
  ranges: SelectionRange[],
  selectedPatchId: string | null,
  palette: ReturnType<typeof viewerPalette>,
  sectionPlane: THREE.Plane | null,
): LineSegments2 | null {
  if (selectedPatchId === null) return null;
  const positions: number[] = [];
  let triangleOffset = 0;
  object.updateMatrixWorld(true);
  object.traverse((child) => {
    if (child.userData.mesh2paramEdgeOverlay === true) return;
    if (!(child instanceof THREE.Mesh) || !(child.geometry instanceof THREE.BufferGeometry)) return;
    const local = patchOutlinePositions(child.geometry, ranges, selectedPatchId, triangleOffset);
    const position = child.geometry.getAttribute("position");
    const index = child.geometry.index;
    triangleOffset += index === null ? Math.floor((position?.count ?? 0) / 3) : Math.floor(index.count / 3);
    const point = new THREE.Vector3();
    for (let item = 0; item + 2 < local.length; item += 3) {
      point.set(local[item]!, local[item + 1]!, local[item + 2]!).applyMatrix4(child.matrixWorld);
      positions.push(point.x, point.y, point.z);
    }
  });
  if (positions.length === 0) return null;
  const geometry = new LineSegmentsGeometry();
  geometry.setPositions(positions);
  const material = new LineMaterial({
    color: new THREE.Color(palette.outline).getHex(),
    linewidth: palette.outlineWidth,
    transparent: true,
    opacity: 0.95,
    depthTest: false,
    depthWrite: false,
    clippingPlanes: sectionPlane === null ? null : [sectionPlane],
  });
  const lines = new LineSegments2(geometry, material);
  lines.renderOrder = 30;
  lines.raycast = () => {};
  return lines;
}

/** Build a display-only triangle overlay from the signed selection map. */
function makePatchHighlight(
  object: THREE.Object3D,
  ranges: SelectionRange[],
  selectedPatchId: string | null,
  palette: ReturnType<typeof viewerPalette>,
  variant: "selected" | "hover" = "selected",
): THREE.Mesh | null {
  const selected = selectedTriangleRanges(ranges, selectedPatchId);
  if (selected.length === 0) return null;
  const positions: number[] = [];
  let triangleOffset = 0;
  object.updateMatrixWorld(true);
  object.traverse((child) => {
    // Edge overlays are LineSegments2, which extends Mesh and carries a decoy `position`
    // attribute, so they pass the guards below and would shift triangleOffset off the surface.
    if (child.userData.mesh2paramEdgeOverlay === true) return;
    if (!(child instanceof THREE.Mesh) || !(child.geometry instanceof THREE.BufferGeometry)) return;
    const position = child.geometry.getAttribute("position");
    if (!isReadableBufferAttribute(position)) return;
    const index = child.geometry.index;
    const triangleCount = index === null ? Math.floor(position.count / 3) : Math.floor(index.count / 3);
    for (const range of selected) {
      const start = Math.max(0, range.triangleStart - triangleOffset);
      const end = Math.min(triangleCount, range.triangleEndExclusive - triangleOffset);
      for (let triangle = start; triangle < end; triangle += 1) {
        for (let corner = 0; corner < 3; corner += 1) {
          const vertex = index?.getX(triangle * 3 + corner) ?? triangle * 3 + corner;
          const point = new THREE.Vector3().fromBufferAttribute(position, vertex).applyMatrix4(child.matrixWorld);
          positions.push(point.x, point.y, point.z);
        }
      }
    }
    triangleOffset += triangleCount;
  });
  if (positions.length === 0) return null;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeVertexNormals();
  const material = variant === "hover"
    ? new THREE.MeshBasicMaterial({
      color: palette.hover,
      transparent: true,
      opacity: palette.hoverOpacity,
      side: THREE.DoubleSide,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -1,
      polygonOffsetUnits: -1,
    })
    : new THREE.MeshStandardMaterial({
      color: palette.highlight,
      emissive: palette.highlightEmissive,
      emissiveIntensity: palette.highlightEmissiveIntensity,
      transparent: true,
      opacity: 0.86,
      side: THREE.DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
    });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.raycast = () => {};
  mesh.renderOrder = variant === "hover" ? 19 : 20;
  return mesh;
}
