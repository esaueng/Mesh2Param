import { Html, Line } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { Box, Camera, Expand, Focus, Grid3X3, Layers3, Ruler, Rotate3D, ScanLine, Slice, View } from "lucide-react";
import {
  Component,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ErrorInfo,
  type MutableRefObject,
  type ReactNode,
} from "react";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { apiClient } from "../api/client";
import type { ArtifactDescriptor, ViewerMode, ViewerPreferences } from "../state/types";
import { ArtifactLayer, type SelectionRange } from "./ArtifactLayer";
import { CameraRig, type CameraCommand } from "./CameraRig";
import type { ViewPreset } from "./cameraMath";
import "./viewer.css";

const MODES: ReadonlyArray<{ id: ViewerMode; label: string }> = [
  { id: "source", label: "Source" },
  { id: "repaired", label: "Repaired" },
  { id: "analysis", label: "Analysis" },
  { id: "patches", label: "Patches" },
  { id: "reconstructed", label: "Reconstructed" },
  { id: "overlay", label: "Overlay" },
  { id: "residual", label: "Heatmap" },
];

interface CadViewportProps {
  projectId: string;
  artifacts: ArtifactDescriptor[];
  preferences: ViewerPreferences;
  selectedPatchId: string | null;
  onPreferences(patch: Partial<ViewerPreferences>): void;
  onSelectPatch(id: string | null): void;
}

export function CadViewport({
  projectId,
  artifacts,
  preferences,
  selectedPatchId,
  onPreferences,
  onSelectPatch,
}: CadViewportProps) {
  const [bounds, setBounds] = useState<THREE.Box3 | null>(null);
  const [command, setCommand] = useState<CameraCommand>({ fitRevision: 0, viewRevision: 0, preset: "iso" });
  const [selection, setSelection] = useState<SelectionRange[]>([]);
  const [sectionEnabled, setSectionEnabled] = useState(false);
  const [measurementEnabled, setMeasurementEnabled] = useState(false);
  const [measurementPoints, setMeasurementPoints] = useState<THREE.Vector3[]>([]);
  const controls = useRef<OrbitControlsImpl | null>(null);
  const artifactMap = useMemo(() => new Map(artifacts.map((artifact) => [artifact.name, artifact])), [artifacts]);
  const selectionArtifact = artifactMap.get("selection-map.json");
  useEffect(() => {
    if (canShow(preferences.mode, artifactMap)) return;
    const fallback = (["source", "reconstructed", "patches", "repaired", "analysis", "residual"] as ViewerMode[])
      .find((mode) => canShow(mode, artifactMap));
    if (fallback !== undefined) onPreferences({ mode: fallback });
  }, [artifactMap, onPreferences, preferences.mode]);

  useEffect(() => {
    if (selectionArtifact === undefined) {
      setSelection([]);
      return;
    }
    const controller = new AbortController();
    void fetch(apiClient.artifactUrl(projectId, selectionArtifact.name, selectionArtifact.sha256), {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error("selection map unavailable");
        return response.json();
      })
      .then((data: unknown) => {
        if (!isSelectionMap(data)) return;
        const patchGlb = artifactMap.get("patches.glb");
        setSelection(patchGlb !== undefined && data.artifact.sha256 === patchGlb.sha256 ? data.ranges : []);
      })
      .catch(() => setSelection([]));
    return () => controller.abort();
  }, [artifactMap, projectId, selectionArtifact]);

  const layers = layersForMode(preferences, artifactMap);
  const artifactKey = layers.map((layer) => layer.artifact.sha256).join("|") || projectId;
  const sectionZ = sectionEnabled && bounds !== null ? bounds.getCenter(new THREE.Vector3()).z : null;
  const sectionPlane = useMemo(() => sectionZ === null
    ? null
    : new THREE.Plane(new THREE.Vector3(0, 0, -1), sectionZ), [sectionZ]);
  const onBounds = useCallback((box: THREE.Box3) => {
    setBounds((current) => {
      const next = current?.clone().union(box) ?? box.clone();
      return current !== null && current.min.equals(next.min) && current.max.equals(next.max) ? current : next;
    });
  }, []);
  useEffect(() => setBounds(null), [artifactKey]);
  useEffect(() => {
    const fit = () => setCommand((current) => ({ ...current, fitRevision: current.fitRevision + 1 }));
    window.addEventListener("mesh2param:fit-view", fit);
    return () => window.removeEventListener("mesh2param:fit-view", fit);
  }, []);

  function preset(value: ViewPreset) {
    setCommand((current) => ({ ...current, preset: value, viewRevision: current.viewRevision + 1 }));
  }

  return (
    <section className="cad-viewport" aria-label="3D CAD viewer" data-testid="cad-viewport">
      <div className="viewport-modebar" role="toolbar" aria-label="Viewer display modes">
        {MODES.map((mode) => (
          <button
            key={mode.id}
            aria-pressed={preferences.mode === mode.id}
            disabled={!canShow(mode.id, artifactMap)}
            onClick={() => onPreferences({ mode: mode.id })}
          >
            <ModeIcon mode={mode.id} />
            <span>{mode.label}</span>
          </button>
        ))}
        <span className="toolbar-separator" />
        <button
          aria-pressed={preferences.shading === "wireframe"}
          onClick={() => onPreferences({ shading: preferences.shading === "wireframe" ? "shaded" : "wireframe" })}
        >
          <Grid3X3 /><span>Edges</span>
        </button>
        <button
          aria-pressed={preferences.projection === "orthographic"}
          onClick={() => onPreferences({
            projection: preferences.projection === "perspective" ? "orthographic" : "perspective",
          })}
        >
          <View /><span>{preferences.projection === "perspective" ? "Ortho" : "Perspective"}</span>
        </button>
        <button onClick={() => setCommand((current) => ({ ...current, fitRevision: current.fitRevision + 1 }))}>
          <Focus /><span>Fit</span>
        </button>
        <button onClick={() => preset("iso")}><Rotate3D /><span>Iso</span></button>
        <label className="standard-view-control">
          <span className="visually-hidden">Standard view</span>
          <select aria-label="Standard view" defaultValue="iso" onChange={(event) => preset(event.currentTarget.value as ViewPreset)}>
            <option value="iso">Iso</option><option value="front">Front</option><option value="back">Back</option>
            <option value="left">Left</option><option value="right">Right</option><option value="top">Top</option><option value="bottom">Bottom</option>
          </select>
        </label>
        <button aria-pressed={sectionEnabled} onClick={() => setSectionEnabled((enabled) => !enabled)} title="Clip at the model mid-plane"><Slice /><span>Section</span></button>
        <button
          aria-pressed={measurementEnabled}
          onClick={() => {
            setMeasurementEnabled((enabled) => !enabled);
            setMeasurementPoints([]);
          }}
          title="Pick two points on the model to create a dimension annotation"
        ><Ruler /><span>Measure</span></button>
        <button
          onClick={() => document.fullscreenElement
            ? void document.exitFullscreen()
            : void document.querySelector(".cad-viewport")?.requestFullscreen()}
        >
          <Expand /><span>Full</span>
        </button>
        <label className="opacity-control">
          <span>Source</span>
          <input
            aria-label="Source opacity"
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={preferences.sourceOpacity}
            onChange={(event) => onPreferences({ sourceOpacity: Number(event.currentTarget.value) })}
          />
        </label>
        <label className="opacity-control">
          <span>Result</span>
          <input
            aria-label="Result opacity"
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={preferences.resultOpacity}
            onChange={(event) => onPreferences({ resultOpacity: Number(event.currentTarget.value) })}
          />
        </label>
      </div>

      <ViewerErrorBoundary key={artifactKey}>
        <Canvas
          frameloop="demand"
          dpr={[1, 1.75]}
          camera={{ position: [90, -110, 85], up: [0, 0, 1], fov: 42, near: 0.01, far: 100_000 }}
          onPointerMissed={() => onSelectPatch(null)}
          onCreated={({ gl }) => {
            gl.localClippingEnabled = true;
            gl.domElement.addEventListener("webglcontextlost", (event) => event.preventDefault());
          }}
        >
          <color attach="background" args={[viewerBackground()]} />
          <ambientLight intensity={1.1} />
          <directionalLight position={[80, -60, 100]} intensity={2.2} />
          <directionalLight position={[-70, 80, 30]} intensity={0.8} />
          <gridHelper
            args={[300, 30, "#173a5b", "#10243a"]}
            rotation={[Math.PI / 2, 0, 0]}
            position={[0, 0, -0.02]}
          />
          <axesHelper args={[35]} />
          <ProjectionController projection={preferences.projection} controlsRef={controls} />
          <Suspense fallback={<Html center className="viewer-loading">Loading geometry…</Html>}>
            {layers.map((layer) => (
              <ArtifactLayer
                key={`${layer.artifact.sha256}-${layer.opacity}-${preferences.shading}`}
                url={apiClient.artifactUrl(projectId, layer.artifact.name, layer.artifact.sha256)}
                mode={layer.mode}
                opacity={layer.opacity}
                wireframe={preferences.shading === "wireframe" || layer.mode === "patches"}
                selectionRanges={layer.mode === "patches" ? selection : []}
                selectedPatchId={selectedPatchId}
                sectionPlane={sectionPlane}
                measurementEnabled={measurementEnabled}
                onBounds={onBounds}
                onMeasurePoint={(point) => setMeasurementPoints((current) => current.length >= 2 ? [point] : [...current, point])}
                {...(layer.mode === "patches" ? { onSelectPatch } : {})}
              />
            ))}
            {measurementPoints.map((point, index) => (
              <mesh key={`${index}-${point.x}-${point.y}-${point.z}`} position={point}>
                <sphereGeometry args={[0.8, 16, 12]} /><meshBasicMaterial color="#f59e0b" depthTest={false} />
              </mesh>
            ))}
            {measurementPoints.length === 2 ? (
              <>
                <Line points={measurementPoints} color="#f59e0b" lineWidth={2} depthTest={false} />
                <Html position={measurementPoints[0]!.clone().lerp(measurementPoints[1]!, 0.5)} center className="dimension-label">
                  {measurementPoints[0]!.distanceTo(measurementPoints[1]!).toFixed(3)} mm
                </Html>
              </>
            ) : null}
          </Suspense>
          <CameraRig bounds={bounds} artifactKey={artifactKey} command={command} controlsRef={controls} />
        </Canvas>
      </ViewerErrorBoundary>

      {layers.length === 0 ? (
        <div className="viewer-empty"><Box /><strong>No geometry artifact</strong><p>Import or load a sample to begin.</p></div>
      ) : null}
      <div className="view-cube" aria-label="Standard views">
        <button onClick={() => preset("top")}>TOP</button>
        <button onClick={() => preset("front")}>FRONT</button>
        <button onClick={() => preset("right")}>RIGHT</button>
      </div>
      <div className="axis-triad" aria-hidden="true">
        <span className="axis-z">Z</span><span className="axis-y">Y</span><span className="axis-x">X</span>
      </div>
      <div className="scale-bar" aria-hidden="true"><span />10 mm</div>
      {selectedPatchId === null ? null : (
        <div className="selection-chip">Selected patch <strong>{selectedPatchId}</strong></div>
      )}
    </section>
  );
}

function ProjectionController({
  projection,
  controlsRef,
}: {
  projection: ViewerPreferences["projection"];
  controlsRef: MutableRefObject<OrbitControlsImpl | null>;
}) {
  const { camera, set, size, invalidate } = useThree();
  const cameras = useMemo(() => ({
    perspective: new THREE.PerspectiveCamera(42, 1, 0.01, 100_000),
    orthographic: new THREE.OrthographicCamera(-100, 100, 100, -100, -100_000, 100_000),
  }), []);
  useEffect(() => {
    const next = cameras[projection];
    if (camera !== next) {
      next.position.copy(camera.position);
      next.quaternion.copy(camera.quaternion);
      next.up.copy(camera.up);
      if (next instanceof THREE.OrthographicCamera) {
        const target = controlsRef.current?.target ?? new THREE.Vector3();
        const distance = Math.max(next.position.distanceTo(target), 1);
        const height = 2 * distance * Math.tan(THREE.MathUtils.degToRad(21));
        next.zoom = size.height / Math.max(height, 0.001);
      }
    }
    if (next instanceof THREE.PerspectiveCamera) {
      next.aspect = size.width / Math.max(size.height, 1);
    } else {
      next.left = -size.width / 2;
      next.right = size.width / 2;
      next.top = size.height / 2;
      next.bottom = -size.height / 2;
    }
    next.updateProjectionMatrix();
    set({ camera: next });
    if (controlsRef.current !== null) controlsRef.current.object = next;
    invalidate();
  }, [camera, cameras, controlsRef, invalidate, projection, set, size]);
  return null;
}

interface DisplayLayer {
  artifact: ArtifactDescriptor;
  opacity: number;
  mode: string;
}

function layersForMode(
  preferences: ViewerPreferences,
  map: Map<string, ArtifactDescriptor>,
): DisplayLayer[] {
  const { mode } = preferences;
  const nameFor: Partial<Record<ViewerMode, string>> = {
    source: "source.glb",
    repaired: "repaired.glb",
    patches: "patches.glb",
    reconstructed: "reconstructed.glb",
    residual: "residual.glb",
    analysis: "analysis-proxy.glb",
  };
  if (mode === "overlay") {
    return [
      { name: "source.glb", opacity: preferences.sourceOpacity, mode: "source" },
      { name: "reconstructed.glb", opacity: preferences.resultOpacity, mode: "reconstructed" },
    ].flatMap((item) => {
      const artifact = map.get(item.name);
      return artifact === undefined ? [] : [{ artifact, opacity: item.opacity, mode: item.mode }];
    });
  }
  const artifact = map.get(nameFor[mode] ?? "");
  const opacity = mode === "source" ? preferences.sourceOpacity : preferences.resultOpacity;
  return artifact === undefined ? [] : [{ artifact, opacity, mode }];
}

function canShow(mode: ViewerMode, map: Map<string, ArtifactDescriptor>): boolean {
  if (mode === "overlay") return map.has("source.glb") && map.has("reconstructed.glb");
  if (mode === "source") return map.has("source.glb");
  const name: Partial<Record<ViewerMode, string>> = {
    repaired: "repaired.glb",
    patches: "patches.glb",
    reconstructed: "reconstructed.glb",
    residual: "residual.glb",
    analysis: "analysis-proxy.glb",
  };
  return map.has(name[mode] ?? "");
}

function ModeIcon({ mode }: { mode: ViewerMode }) {
  if (mode === "overlay") return <Layers3 />;
  if (mode === "residual") return <ScanLine />;
  if (mode === "patches") return <Grid3X3 />;
  if (mode === "reconstructed") return <Box />;
  return <Camera />;
}

function isSelectionMap(value: unknown): value is { artifact: { sha256: string }; ranges: SelectionRange[] } {
  if (value === null || typeof value !== "object") return false;
  const raw = value as Record<string, unknown>;
  return Boolean(
    raw.artifact
    && typeof raw.artifact === "object"
    && typeof (raw.artifact as Record<string, unknown>).sha256 === "string"
    && Array.isArray(raw.ranges),
  );
}

function viewerBackground(): string {
  if (typeof document === "undefined") return "#070b10";
  return getComputedStyle(document.documentElement).getPropertyValue("--color-viewport").trim() || "#070b10";
}

class ViewerErrorBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(error: unknown) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Mesh2Param viewer error", error, info);
  }
  render() {
    return this.state.error === null ? this.props.children : (
      <div className="viewer-error" role="alert">
        <strong>Viewer could not load geometry</strong><span>{this.state.error}</span>
      </div>
    );
  }
}
