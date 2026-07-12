import * as THREE from "three";

export type ViewPreset = "iso" | "front" | "back" | "left" | "right" | "top" | "bottom";
export interface CameraFit { position: THREE.Vector3; target: THREE.Vector3; up: THREE.Vector3 }

const DIRECTIONS: Record<ViewPreset, [number, number, number]> = {
  iso: [1, 1, 1],
  front: [0, -1, 0],
  back: [0, 1, 0],
  left: [-1, 0, 0],
  right: [1, 0, 0],
  top: [0, 0, 1],
  bottom: [0, 0, -1],
};

export function cameraFitForDirection(
  box: THREE.Box3,
  fovDegrees: number,
  aspect: number,
  viewDirection: [number, number, number],
  margin = 1.2,
): CameraFit {
  const center = box.getCenter(new THREE.Vector3());
  const direction = new THREE.Vector3(...viewDirection).normalize();
  const up = cameraUpForDirection(direction);
  const projected = projectedBoxSize(box, direction, up);
  const vertical = Math.max(Math.tan(THREE.MathUtils.degToRad(fovDegrees / 2)), 0.05);
  const horizontal = vertical * Math.max(aspect, 0.1);
  const distance = projected.depth / 2 + margin * Math.max(
    projected.height / 2 / vertical,
    projected.width / 2 / horizontal,
    1e-3,
  );
  return { position: center.clone().addScaledVector(direction, distance), target: center, up };
}

export function cameraFitForBox(
  box: THREE.Box3,
  fovDegrees: number,
  aspect: number,
  preset: ViewPreset = "iso",
  margin = 1.2,
): CameraFit {
  return cameraFitForDirection(box, fovDegrees, aspect, DIRECTIONS[preset], margin);
}

export function orthographicZoomForBox(
  box: THREE.Box3,
  viewportWidth: number,
  viewportHeight: number,
  viewDirection: [number, number, number],
  margin = 1.2,
): number {
  const direction = new THREE.Vector3(...viewDirection).normalize();
  const projected = projectedBoxSize(box, direction, cameraUpForDirection(direction));
  return Math.max(Math.min(
    viewportWidth / Math.max(projected.width * margin, 1e-3),
    viewportHeight / Math.max(projected.height * margin, 1e-3),
  ), 1e-6);
}

function cameraUpForDirection(direction: THREE.Vector3): THREE.Vector3 {
  const worldUp = new THREE.Vector3(0, 0, 1);
  return Math.abs(direction.z) > 0.98
    ? new THREE.Vector3(-1, 0, 0)
    : worldUp.projectOnPlane(direction).normalize();
}

function projectedBoxSize(box: THREE.Box3, direction: THREE.Vector3, up: THREE.Vector3) {
  const right = new THREE.Vector3().crossVectors(up, direction).normalize();
  let minRight = Infinity;
  let maxRight = -Infinity;
  let minUp = Infinity;
  let maxUp = -Infinity;
  let minDepth = Infinity;
  let maxDepth = -Infinity;
  for (const x of [box.min.x, box.max.x]) {
    for (const y of [box.min.y, box.max.y]) {
      for (const z of [box.min.z, box.max.z]) {
        const corner = new THREE.Vector3(x, y, z);
        const horizontal = corner.dot(right);
        const vertical = corner.dot(up);
        const depth = corner.dot(direction);
        minRight = Math.min(minRight, horizontal);
        maxRight = Math.max(maxRight, horizontal);
        minUp = Math.min(minUp, vertical);
        maxUp = Math.max(maxUp, vertical);
        minDepth = Math.min(minDepth, depth);
        maxDepth = Math.max(maxDepth, depth);
      }
    }
  }
  return { width: maxRight - minRight, height: maxUp - minUp, depth: maxDepth - minDepth };
}

export function shouldFitCamera(previousArtifactKey:string|null,nextArtifactKey:string,explicitFitRevision:number,appliedFitRevision:number){return previousArtifactKey!==nextArtifactKey||explicitFitRevision!==appliedFitRevision}
export interface ScaleBarSpec{value:number;width:number}
/** Snap the viewport scale bar to a 1-2-5 decade length whose on-screen width lands near targetPx. */
export function scaleBarForPixelsPerUnit(pxPerUnit:number,targetPx=94):ScaleBarSpec|null{if(!Number.isFinite(pxPerUnit)||pxPerUnit<=0)return null;const raw=targetPx/pxPerUnit;const pow=10**Math.floor(Math.log10(raw));const value=[1,2,5,10].map((step)=>Number((step*pow).toPrecision(12))).reduce((best,candidate)=>Math.abs(candidate-raw)<Math.abs(best-raw)?candidate:best);return{value,width:Math.round(value*pxPerUnit)}}
