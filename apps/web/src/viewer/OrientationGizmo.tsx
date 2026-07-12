import { Billboard, GizmoHelper, Line, Text } from "@react-three/drei";
import gizmoFontUrl from "@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff?url";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { configureTextBuilder } from "troika-three-text";

// Troika's worker typesetter rebuilds code with new Function(), which the
// production CSP blocks. Keep the OpenCAE gizmo labels on the main thread.
configureTextBuilder({ useWorker: false });

export type ViewCubeCornerDirection = [number, number, number];
export type GizmoViewRequest = "x" | "y" | "z" | "iso" | { kind: "corner"; direction: ViewCubeCornerDirection };
export type ViewCubeFaceLabel = "Front" | "Back" | "Right" | "Left" | "Top" | "Bottom";

export const VIEWER_GIZMO_ALIGNMENT = "bottom-right";
export const VIEWER_GIZMO_MARGIN: [number, number] = [112, 112];
export const VIEWER_GIZMO_SCALE = 40;
export const VIEWER_AXIS_HEAD_RADIUS = 0.26;
export const VIEWER_AXIS_LABEL_BADGE_RADIUS = 0.18;
export const VIEWER_AXIS_LABEL_BADGE_COLOR = "#07111d";
export const VIEWER_AXIS_LABEL_FONT_SIZE = 0.24;
export const VIEWER_AXIS_LABEL_FONT_WEIGHT = 800;
export const VIEWER_AXIS_LABEL_COLOR = "#ffffff";
export const VIEWER_AXIS_LABEL_OUTLINE_COLOR = "#07111d";
export const VIEWER_AXIS_LABEL_OUTLINE_WIDTH = 0.028;
export const VIEWER_GIZMO_AXIS_LENGTH = 1.75;
export const VIEWER_GIZMO_LABEL_DISTANCE = 1.9;
export const VIEWER_VIEW_CUBE_SIZE = 1.2;
export const VIEWER_VIEW_CUBE_BODY_OPACITY = 1;
export const VIEWER_VIEW_CUBE_FACE_OPACITY = 0.62;
export const VIEWER_VIEW_CUBE_FACE_HOVER_OPACITY = 0.78;
export const VIEWER_VIEW_CUBE_EDGE_COLOR = "#8fb4d8";
export const VIEWER_VIEW_CUBE_FACE_LABEL_FONT_SIZE = 0.32;
export const VIEWER_VIEW_CUBE_CORNER_RADIUS = 0.082;
export const VIEWER_VIEW_CUBE_CORNER_HIT_RADIUS = 0.19;
const VIEWER_VIEW_CUBE_FACE_VISIBILITY_THRESHOLD = 0;

export function viewerGizmoLayout() {
  const cubeSize = VIEWER_VIEW_CUBE_SIZE;
  const contentCenter: [number, number, number] = [VIEWER_GIZMO_LABEL_DISTANCE / 2, VIEWER_GIZMO_LABEL_DISTANCE / 2, VIEWER_GIZMO_LABEL_DISTANCE / 2];
  return {
    origin: [0, 0, 0] as [number, number, number],
    cubeMin: [0, 0, 0] as [number, number, number],
    cubeMax: [cubeSize, cubeSize, cubeSize] as [number, number, number],
    cubeCenter: [cubeSize / 2, cubeSize / 2, cubeSize / 2] as [number, number, number],
    contentCenter,
    contentOffset: contentCenter.map((value) => -value) as [number, number, number],
    axisCapPositions: {
      x: [VIEWER_GIZMO_LABEL_DISTANCE, 0, 0] as [number, number, number],
      y: [0, VIEWER_GIZMO_LABEL_DISTANCE, 0] as [number, number, number],
      z: [0, 0, VIEWER_GIZMO_LABEL_DISTANCE] as [number, number, number],
    },
  };
}

export function OrientationGizmo({ onSelectView }: { onSelectView: (view: GizmoViewRequest) => void }) {
  return <GizmoHelper alignment={VIEWER_GIZMO_ALIGNMENT} margin={VIEWER_GIZMO_MARGIN}><CleanAxisGizmo onSelectView={onSelectView} /></GizmoHelper>;
}

function CleanAxisGizmo({ onSelectView }: { onSelectView: (view: GizmoViewRequest) => void }) {
  const layout = viewerGizmoLayout();
  return (
    <group scale={VIEWER_GIZMO_SCALE}>
      <group position={layout.contentOffset}>
        <PositiveOctantViewCube onSelectView={onSelectView} />
        {GIZMO_AXES.map((axis) => <GizmoAxis key={axis.label} {...axis} onSelectView={onSelectView} />)}
        <IsoOriginButton onSelectView={onSelectView} />
      </group>
    </group>
  );
}

const GIZMO_AXES: Array<{ label: "X" | "Y" | "Z"; color: string; target: "x" | "y" | "z"; direction: [number, number, number] }> = [
  { label: "X", color: "#ff4b7d", target: "x", direction: [1, 0, 0] },
  { label: "Y", color: "#2ddc94", target: "y", direction: [0, 1, 0] },
  { label: "Z", color: "#4da3ff", target: "z", direction: [0, 0, 1] },
];

function GizmoAxis({ label, color, target, direction, onSelectView }: (typeof GIZMO_AXES)[number] & { onSelectView: (view: GizmoViewRequest) => void }) {
  const [hovered, setHovered] = useState(false);
  const origin = viewerGizmoLayout().origin;
  const lineEnd = direction.map((value) => value * VIEWER_GIZMO_AXIS_LENGTH) as [number, number, number];
  const capPosition = direction.map((value) => value * VIEWER_GIZMO_LABEL_DISTANCE) as [number, number, number];
  return (
    <group>
      <Line points={[origin, lineEnd]} color={color} lineWidth={hovered ? 4 : 3} transparent opacity={hovered ? 1 : 0.85} depthTest={false} />
      <AxisCap label={label} color={color} position={capPosition} target={target} hovered={hovered} onHoverChange={setHovered} onSelectView={onSelectView} />
    </group>
  );
}

function AxisCap({ label, color, position, target, hovered, onHoverChange, onSelectView }: {
  label: "X" | "Y" | "Z"; color: string; position: [number, number, number]; target: "x" | "y" | "z"; hovered: boolean;
  onHoverChange: (hovered: boolean) => void; onSelectView: (view: GizmoViewRequest) => void;
}) {
  const title = `View +${label}`;
  return (
    <Billboard name={title} position={position} scale={hovered ? 1.08 : 1} userData={{ title, ariaLabel: title }}
      onPointerDown={(event: ThreeEvent<PointerEvent>) => event.stopPropagation()}
      onClick={(event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); onSelectView(target); }}
      onPointerOver={(event: ThreeEvent<PointerEvent>) => { event.stopPropagation(); onHoverChange(true); }}
      onPointerOut={(event: ThreeEvent<PointerEvent>) => { event.stopPropagation(); onHoverChange(false); }}>
      {hovered ? <mesh position={[0, 0, -0.002]}><ringGeometry args={[VIEWER_AXIS_HEAD_RADIUS * 1.02, VIEWER_AXIS_HEAD_RADIUS * 1.18, 40]} /><meshBasicMaterial color="#f8fbff" depthTest={false} transparent opacity={0.38} toneMapped={false} /></mesh> : null}
      <mesh><ringGeometry args={[VIEWER_AXIS_LABEL_BADGE_RADIUS, VIEWER_AXIS_HEAD_RADIUS, 40]} /><meshBasicMaterial color={color} depthTest={false} toneMapped={false} /></mesh>
      <mesh position={[0, 0, 0.004]}><circleGeometry args={[VIEWER_AXIS_LABEL_BADGE_RADIUS, 36]} /><meshBasicMaterial color={VIEWER_AXIS_LABEL_BADGE_COLOR} depthTest={false} toneMapped={false} /></mesh>
      <Text anchorX="center" anchorY="middle" color={VIEWER_AXIS_LABEL_COLOR} font={gizmoFontUrl} fontSize={VIEWER_AXIS_LABEL_FONT_SIZE} fontWeight={VIEWER_AXIS_LABEL_FONT_WEIGHT} letterSpacing={0} outlineColor={VIEWER_AXIS_LABEL_OUTLINE_COLOR} outlineWidth={VIEWER_AXIS_LABEL_OUTLINE_WIDTH} position={[0, 0, 0.01]}>{label}</Text>
      <Text anchorX="center" anchorY="middle" color="#d7e3ee" font={gizmoFontUrl} fontSize={0.105} letterSpacing={0} outlineColor={VIEWER_AXIS_LABEL_OUTLINE_COLOR} outlineWidth={0.01} position={[0, -0.095, 0.011]}>+</Text>
    </Billboard>
  );
}

function PositiveOctantViewCube({ onSelectView }: { onSelectView: (view: GizmoViewRequest) => void }) {
  const cubeSize = VIEWER_VIEW_CUBE_SIZE;
  const half = cubeSize / 2;
  const faces = useMemo(() => getViewCubeFaceDescriptors(), []);
  const corners = useMemo(() => getViewCubeCornerDescriptors(), []);
  return (
    <group name="Positive-octant triad view cube">
      <mesh position={[half, half, half]} renderOrder={1}><boxGeometry args={[cubeSize, cubeSize, cubeSize]} /><meshBasicMaterial color="#1d2b3d" depthTest transparent={false} opacity={VIEWER_VIEW_CUBE_BODY_OPACITY} depthWrite toneMapped={false} /></mesh>
      <ViewCubeEdges />
      {faces.map((face) => <ViewCubeFace key={face.label} {...face} onSelectView={onSelectView} />)}
      {corners.map((corner) => <ViewCubeCorner key={corner.title} {...corner} onSelectView={onSelectView} />)}
    </group>
  );
}

export interface ViewCubeFaceDescriptor { label: ViewCubeFaceLabel; position: [number, number, number]; rotation: [number, number, number]; normal: [number, number, number]; }

export function getViewCubeFaceDescriptors(): ViewCubeFaceDescriptor[] {
  const cubeSize = VIEWER_VIEW_CUBE_SIZE;
  const faceOffset = 0.006;
  const half = cubeSize / 2;
  return [
    { label: "Front", position: [half, cubeSize + faceOffset, half], rotation: [-Math.PI / 2, 0, -Math.PI], normal: [0, 1, 0] },
    { label: "Back", position: [half, -faceOffset, half], rotation: [Math.PI / 2, 0, 0], normal: [0, -1, 0] },
    { label: "Left", position: [cubeSize + faceOffset, half, half], rotation: [Math.PI / 2, Math.PI / 2, 0], normal: [1, 0, 0] },
    { label: "Right", position: [-faceOffset, half, half], rotation: [Math.PI / 2, -Math.PI / 2, 0], normal: [-1, 0, 0] },
    { label: "Top", position: [half, half, cubeSize + faceOffset], rotation: [0, 0, Math.PI / 2], normal: [0, 0, 1] },
    { label: "Bottom", position: [half, half, -faceOffset], rotation: [-Math.PI, 0, -Math.PI / 2], normal: [0, 0, -1] },
  ];
}

export interface ViewCubeCornerDescriptor { title: string; position: [number, number, number]; direction: ViewCubeCornerDirection; }

export function getViewCubeCornerDescriptors(): ViewCubeCornerDescriptor[] {
  const cubeSize = VIEWER_VIEW_CUBE_SIZE;
  const signs = [-1, 1] as const;
  const axisTitle = (axis: "X" | "Y" | "Z", sign: -1 | 1) => `${sign > 0 ? "+" : "-"}${axis}`;
  return signs.flatMap((x) => signs.flatMap((y) => signs.map((z) => ({
    title: `View ${axisTitle("X", x)} ${axisTitle("Y", y)} ${axisTitle("Z", z)}`,
    position: [x > 0 ? cubeSize : 0, y > 0 ? cubeSize : 0, z > 0 ? cubeSize : 0] as [number, number, number],
    direction: [x, y, z] as ViewCubeCornerDirection,
  }))));
}

function ViewCubeEdges() {
  const edgeInset = 0.004;
  const min = -edgeInset;
  const max = VIEWER_VIEW_CUBE_SIZE + edgeInset;
  const segments: Array<[[number, number, number], [number, number, number]]> = [
    [[min, min, min], [max, min, min]], [[min, max, min], [max, max, min]], [[min, min, max], [max, min, max]], [[min, max, max], [max, max, max]],
    [[min, min, min], [min, max, min]], [[max, min, min], [max, max, min]], [[min, min, max], [min, max, max]], [[max, min, max], [max, max, max]],
    [[min, min, min], [min, min, max]], [[max, min, min], [max, min, max]], [[min, max, min], [min, max, max]], [[max, max, min], [max, max, max]],
  ];
  return <group renderOrder={2}>{segments.map((segment, index) => <Line key={index} points={segment} color={VIEWER_VIEW_CUBE_EDGE_COLOR} lineWidth={1} transparent opacity={0.56} depthTest />)}</group>;
}

function ViewCubeFace({ label, position, rotation, normal, onSelectView }: ViewCubeFaceDescriptor & { onSelectView: (view: GizmoViewRequest) => void }) {
  const [hovered, setHovered] = useState(false);
  const { camera } = useThree();
  const faceRef = useRef<THREE.Group | null>(null);
  const labelRef = useRef<THREE.Group | null>(null);
  const localNormal = useMemo(() => new THREE.Vector3(...normal), [normal]);
  const faceNormalWorldRef = useRef(new THREE.Vector3());
  const toCameraWorldRef = useRef(new THREE.Vector3());
  const normalMatrixRef = useRef(new THREE.Matrix3());
  const title = `${label} view`;
  useFrame(() => {
    const labelObject = labelRef.current;
    const cubeRootObject = faceRef.current?.parent;
    if (!labelObject || !cubeRootObject) return;
    const faceNormalWorld = faceNormalWorldRef.current.copy(localNormal).applyNormalMatrix(normalMatrixRef.current.getNormalMatrix(cubeRootObject.matrixWorld)).normalize();
    const toCameraWorld = camera.getWorldDirection(toCameraWorldRef.current).negate().normalize();
    labelObject.visible = shouldShowViewCubeFaceLabel(faceNormalWorld, toCameraWorld);
  });
  return (
    <group ref={faceRef} name={title} position={position} rotation={rotation} userData={{ title, ariaLabel: title }}
      onPointerDown={(event: ThreeEvent<PointerEvent>) => event.stopPropagation()}
      onClick={(event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); onSelectView(viewCubeFaceToGizmoView(label)); }}
      onPointerOver={(event: ThreeEvent<PointerEvent>) => { event.stopPropagation(); setHovered(true); }}
      onPointerOut={(event: ThreeEvent<PointerEvent>) => { event.stopPropagation(); setHovered(false); }}>
      <mesh renderOrder={3}><planeGeometry args={[VIEWER_VIEW_CUBE_SIZE * 0.82, VIEWER_VIEW_CUBE_SIZE * 0.82]} /><meshBasicMaterial color={hovered ? "#6da4c9" : "#31516b"} depthTest transparent opacity={hovered ? VIEWER_VIEW_CUBE_FACE_HOVER_OPACITY : VIEWER_VIEW_CUBE_FACE_OPACITY} depthWrite={false} toneMapped={false} /></mesh>
      <group ref={labelRef} position={[0, 0, 0.075]} renderOrder={4}><GizmoTextLabel color={hovered ? "#ffffff" : "#e4eef8"} fontSize={VIEWER_VIEW_CUBE_FACE_LABEL_FONT_SIZE} opacity={hovered ? 1 : 0.95} depthTest>{label}</GizmoTextLabel></group>
    </group>
  );
}

function ViewCubeCorner({ title, position, direction, onSelectView }: ViewCubeCornerDescriptor & { onSelectView: (view: GizmoViewRequest) => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <Billboard name={title} position={position} scale={hovered ? 1.22 : 1} userData={{ title, ariaLabel: title }}
      onPointerDown={(event: ThreeEvent<PointerEvent>) => event.stopPropagation()}
      onClick={(event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); onSelectView({ kind: "corner", direction }); }}
      onPointerOver={(event: ThreeEvent<PointerEvent>) => { event.stopPropagation(); setHovered(true); }}
      onPointerOut={(event: ThreeEvent<PointerEvent>) => { event.stopPropagation(); setHovered(false); }}>
      <mesh renderOrder={3}><sphereGeometry args={[VIEWER_VIEW_CUBE_CORNER_HIT_RADIUS, 18, 18]} /><meshBasicMaterial color="#ffffff" depthTest={false} transparent opacity={0} toneMapped={false} /></mesh>
      <mesh renderOrder={5}><sphereGeometry args={[VIEWER_VIEW_CUBE_CORNER_RADIUS, 18, 18]} /><meshBasicMaterial color={hovered ? "#f8fbff" : "#a9c9e8"} depthTest={false} transparent opacity={hovered ? 0.96 : 0.78} toneMapped={false} /></mesh>
      {hovered ? <mesh renderOrder={4}><sphereGeometry args={[VIEWER_VIEW_CUBE_CORNER_RADIUS * 1.7, 18, 18]} /><meshBasicMaterial color="#f8fbff" depthTest={false} transparent opacity={0.22} toneMapped={false} /></mesh> : null}
    </Billboard>
  );
}

function IsoOriginButton({ onSelectView }: { onSelectView: (view: GizmoViewRequest) => void }) {
  const [hovered, setHovered] = useState(false);
  const half = VIEWER_VIEW_CUBE_SIZE / 2;
  return (
    <Billboard name="Isometric view" position={[half, half, half]} userData={{ title: "Isometric view", ariaLabel: "Isometric view" }}
      onPointerDown={(event: ThreeEvent<PointerEvent>) => event.stopPropagation()}
      onClick={(event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); onSelectView("iso"); }}
      onPointerOver={(event: ThreeEvent<PointerEvent>) => { event.stopPropagation(); setHovered(true); }}
      onPointerOut={(event: ThreeEvent<PointerEvent>) => { event.stopPropagation(); setHovered(false); }}>
      {hovered ? <mesh><ringGeometry args={[0.075, 0.105, 28]} /><meshBasicMaterial color="#f8fbff" depthTest={false} transparent opacity={0.42} toneMapped={false} /></mesh> : null}
      <mesh><sphereGeometry args={[0.065, 18, 18]} /><meshBasicMaterial color="#d9e8f6" depthTest={false} toneMapped={false} /></mesh>
      {hovered ? <GizmoTextLabel color="#f8fbff" fontSize={0.095} position={[0, -0.16, 0.01]}>Iso</GizmoTextLabel> : null}
    </Billboard>
  );
}

function GizmoTextLabel({ children, color, fontSize, depthTest = false, opacity = 1, position = [0, 0, 0.01] }: {
  children: string; color: string; fontSize: number; depthTest?: boolean; opacity?: number; position?: [number, number, number];
}) {
  return <Text anchorX="center" anchorY="middle" color={color} fillOpacity={opacity} font={gizmoFontUrl} fontSize={fontSize} frustumCulled={false} letterSpacing={0} material-depthTest={depthTest} material-side={THREE.DoubleSide} material-toneMapped={false} outlineColor="#07111d" outlineOpacity={opacity} outlineWidth={0.014} position={position} renderOrder={5}>{children}</Text>;
}

export function shouldShowViewCubeFaceLabel(faceNormalWorld: THREE.Vector3, toCameraWorld: THREE.Vector3, threshold = VIEWER_VIEW_CUBE_FACE_VISIBILITY_THRESHOLD) {
  return faceNormalWorld.clone().normalize().dot(toCameraWorld.clone().normalize()) > threshold;
}

export function viewCubeFaceToGizmoView(label: ViewCubeFaceLabel): "x" | "y" | "z" {
  if (label === "Front" || label === "Back") return "y";
  if (label === "Right" || label === "Left") return "x";
  return "z";
}
