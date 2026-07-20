import * as THREE from "three";

export function sectionPlaneForBounds(
  bounds: THREE.Box3,
  direction: THREE.Vector3,
  position: number,
): THREE.Plane | null {
  if (bounds.isEmpty() || !Number.isFinite(position)) return null;
  const normal = direction.clone();
  if (normal.lengthSq() <= 1e-24) return null;
  normal.normalize();
  const center = bounds.getCenter(new THREE.Vector3());
  const half = bounds.getSize(new THREE.Vector3()).multiplyScalar(0.5);
  const projectedHalfExtent = Math.abs(normal.x) * half.x
    + Math.abs(normal.y) * half.y
    + Math.abs(normal.z) * half.z;
  const fraction = THREE.MathUtils.clamp(position, -1, 1);
  const point = center.clone().addScaledVector(normal, fraction * projectedHalfExtent);
  return new THREE.Plane(normal, -normal.dot(point));
}
