import { OrbitControls } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useRef, type MutableRefObject } from "react";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { cameraFitForBox, cameraFitForDirection, type ViewPreset } from "./cameraMath";

export interface CameraCommand {
  fitRevision: number;
  viewRevision: number;
  preset: ViewPreset;
  direction: [number, number, number] | null;
}

interface CameraRigProps {
  bounds: THREE.Box3 | null;
  artifactKey: string;
  command: CameraCommand;
  controlsRef: MutableRefObject<OrbitControlsImpl | null>;
}

export function CameraRig({ bounds, artifactKey, command, controlsRef }: CameraRigProps) {
  const { camera, invalidate, size } = useThree();
  const sizeRef = useRef(size);
  const contentRef = useRef<string | null>(null);
  const fitRef = useRef(-1);
  const viewRef = useRef(-1);

  useEffect(() => {
    sizeRef.current = size;
    if (camera instanceof THREE.PerspectiveCamera) {
      camera.aspect = size.width / Math.max(size.height, 1);
      camera.updateProjectionMatrix();
      invalidate();
    } else if (camera instanceof THREE.OrthographicCamera) {
      camera.updateProjectionMatrix();
      invalidate();
    }
  }, [camera, invalidate, size]);

  useEffect(() => {
    if (bounds === null || bounds.isEmpty()) return;
    const contentChanged = contentRef.current !== artifactKey;
    const explicitFit = fitRef.current !== command.fitRevision;
    const viewChanged = viewRef.current !== command.viewRevision;
    if (!contentChanged && !explicitFit && !viewChanged) return;
    contentRef.current = artifactKey;
    fitRef.current = command.fitRevision;
    viewRef.current = command.viewRevision;
    const currentSize = sizeRef.current;
    const fov = camera instanceof THREE.PerspectiveCamera ? camera.fov : 42;
    const aspect = currentSize.width / Math.max(currentSize.height, 1);
    const fit = viewChanged && command.direction !== null
      ? cameraFitForDirection(bounds, fov, aspect, command.direction)
      : cameraFitForBox(bounds, fov, aspect, viewChanged ? command.preset : "iso");
    camera.position.copy(fit.position);
    camera.up.copy(fit.up);
    camera.lookAt(fit.target);
    camera.updateMatrixWorld();
    if (camera instanceof THREE.PerspectiveCamera || camera instanceof THREE.OrthographicCamera) {
      camera.updateProjectionMatrix();
    }
    if (controlsRef.current !== null) {
      controlsRef.current.target.copy(fit.target);
      controlsRef.current.update();
    }
    invalidate();
  }, [artifactKey, bounds, camera, command.direction, command.fitRevision, command.preset, command.viewRevision, controlsRef, invalidate]);

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.12}
      screenSpacePanning
      onChange={() => invalidate()}
    />
  );
}
