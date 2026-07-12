import { useGLTF } from "@react-three/drei";
import type { ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import * as THREE from "three";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { GLTF } from "three-stdlib";
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

export function usesAnalyticResultShading(mode: string): boolean {
  return mode === "reconstructed";
}

interface ArtifactLayerProps {
  url: string;
  mode: string;
  opacity: number;
  wireframe: boolean;
  theme: ViewerTheme;
  selectionRanges: SelectionRange[];
  selectedPatchId: string | null;
  sectionPlane: THREE.Plane | null;
  measurementEnabled: boolean;
  onBounds(box: THREE.Box3): void;
  onSelectPatch?(id: string): void;
  onMeasurePoint?(point: THREE.Vector3): void;
}

export function ArtifactLayer({
  url,
  mode,
  opacity,
  wireframe,
  theme,
  selectionRanges,
  selectedPatchId,
  sectionPlane,
  measurementEnabled,
  onBounds,
  onSelectPatch,
  onMeasurePoint,
}: ArtifactLayerProps) {
  const gltf = useGLTF(url) as GLTF;
  const palette = viewerPalette(theme);
  const object = useMemo(() => {
    const clone = gltf.scene.clone(true);
    clone.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      if (usesAnalyticResultShading(mode) && child.geometry instanceof THREE.BufferGeometry) {
        child.geometry = toCreasedNormals(child.geometry, Math.PI / 6);
        child.geometry.userData.mesh2paramOwned = true;
      }
      const source = Array.isArray(child.material) ? child.material[0] : child.material;
      const material = (source ?? new THREE.MeshStandardMaterial()).clone();
      material.transparent = opacity < 1;
      material.opacity = opacity;
      material.depthWrite = opacity > 0.55;
      material.wireframe = wireframe;
      material.side = THREE.DoubleSide;
      material.clippingPlanes = sectionPlane === null ? null : [sectionPlane];
      if (material instanceof THREE.MeshStandardMaterial) {
        material.flatShading = !usesAnalyticResultShading(mode);
        material.roughness = 0.72;
        material.metalness = 0.04;
        const color = surfaceColor(mode, palette);
        if (color !== null) material.color = new THREE.Color(color);
        material.needsUpdate = true;
      }
      if (mode === "patches") material.vertexColors = false;
      child.material = material;
    });
    return clone;
  }, [gltf.scene, mode, opacity, palette, sectionPlane, wireframe]);

  const highlight = useMemo(
    () => mode === "patches" ? makePatchHighlight(object, selectionRanges, selectedPatchId, palette) : null,
    [mode, object, palette, selectedPatchId, selectionRanges],
  );

  useEffect(() => {
    const box = new THREE.Box3().setFromObject(object);
    if (!box.isEmpty()) onBounds(box);
    return () => {
      object.traverse((child) => {
        if (!(child instanceof THREE.Mesh)) return;
        if (child.geometry.userData.mesh2paramOwned === true) child.geometry.dispose();
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        for (const material of materials) material.dispose();
      });
    };
  }, [object, onBounds]);

  useEffect(() => () => {
    highlight?.geometry.dispose();
    const material = highlight?.material;
    if (Array.isArray(material)) material.forEach((item) => item.dispose());
    else material?.dispose();
  }, [highlight]);

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
      <primitive object={object} onClick={select} />
      {highlight === null ? null : <primitive object={highlight} data-testid="selected-patch-highlight" />}
    </group>
  );
}

/** Build a display-only triangle overlay from the signed selection map. */
function makePatchHighlight(
  object: THREE.Object3D,
  ranges: SelectionRange[],
  selectedPatchId: string | null,
  palette: ReturnType<typeof viewerPalette>,
): THREE.Mesh | null {
  const selected = selectedTriangleRanges(ranges, selectedPatchId);
  if (selected.length === 0) return null;
  const positions: number[] = [];
  let triangleOffset = 0;
  object.updateMatrixWorld(true);
  object.traverse((child) => {
    if (!(child instanceof THREE.Mesh) || !(child.geometry instanceof THREE.BufferGeometry)) return;
    const position = child.geometry.getAttribute("position");
    if (!(position instanceof THREE.BufferAttribute)) return;
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
  const material = new THREE.MeshStandardMaterial({
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
  mesh.renderOrder = 20;
  return mesh;
}
