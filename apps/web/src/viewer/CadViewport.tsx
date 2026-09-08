import { Html, Line } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Box, Camera, Expand, Focus, Grid3X3, Layers3, LoaderCircle, Ruler, Rotate3D, ScanLine, Slice, View } from "lucide-react";
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
import { apiFetch } from "../api/auth";
import { debugLog } from "../canvas/debugLog";
import type { ArtifactDescriptor, Units, ViewerMode, ViewerPreferences } from "../state/types";
import { ArtifactLayer, type SelectionRange } from "./ArtifactLayer";
import { CameraRig, type CameraCommand } from "./CameraRig";
import { OrientationGizmoCanvas, type GizmoViewRequest } from "./OrientationGizmo";
import { scaleBarForPixelsPerUnit, type ScaleBarSpec, type ViewPreset } from "./cameraMath";
import { MODE_GEOMETRY, OVERLAY_GEOMETRY, VIEWER_MODE_FALLBACK_ORDER } from "./geometryPrefetch";
import { geometryArtifactUrls, releaseProjectGltfCache, syncProjectGltfCache } from "./gltfCache";
import { measurementLabel, requiredMeasurementPoints, type MeasurementMode, type Point3 } from "./measurements";
import { sectionPlaneForBounds } from "./sectionPlane";
import { viewerPalette, type ViewerTheme } from "./viewerTheme";
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

/**
 * Keep screen-space viewer chrome crisp on HiDPI displays. Dense geometry still
 * gets a lower pixel ratio, but no longer forces the whole canvas (including the
 * orientation gizmo) down to a visibly pixelated 1x backing buffer.
 */
/**
 * How long the reveal may wait on a frame that never arrives. Well beyond the
 * slowest observed shader compile, and only a backstop: the normal path is the
 * frame counter below.
 */
const REVEAL_FAILSAFE_MS = 6_000;
const NO_SELECTION_RANGES: SelectionRange[] = [];
const NO_HIDDEN_PATCH_IDS: string[] = [];

/**
 * Reports once the current artifact has actually been drawn.
 *
 * react-three-fiber runs useFrame callbacks before rendering the frame they
 * belong to, so the second callback is the first moment at which a frame
 * containing this artifact is known to have reached the screen.
 */
function FramePainted({ onPainted }: { onPainted(): void }) {
  const frames = useRef(0);
  const reported = useRef(false);
  useFrame(() => {
    if (reported.current) return;
    frames.current += 1;
    if (frames.current < 2) return;
    reported.current = true;
    onPainted();
  });
  return null;
}

export function viewerDpr(denseMesh: boolean): number {
  return denseMesh ? 1.5 : 2;
}

interface CadViewportProps {
  projectId: string;
  units: Units;
  artifacts: ArtifactDescriptor[];
  preferences: ViewerPreferences;
  theme: ViewerTheme;
  denseMesh?: boolean;
  sourceProxyActive?: boolean;
  hiddenPatchIds?: readonly string[];
  selectedPatchId: string | null;
  /** Patch under the pointer, in the viewport or in the patch list; rendering only. */
  hoveredPatchId?: string | null;
  /** Reference grid on the model's floor plane. */
  grid?: boolean;
  onPreferences(patch: Partial<ViewerPreferences>): void;
  onSelectPatch(id: string | null): void;
  onHoverPatch?(id: string | null): void;
  /** "minimal" hides the built-in mode bar so an external control (e.g. the command dock) can drive the viewer. */
  chrome?: "full" | "minimal";
}

export function CadViewport(props: CadViewportProps) {
  // Resolving browser artifact URLs can fail before the canvas is mounted.
  const resetKey = `${props.projectId}:${props.artifacts.map((artifact) => `${artifact.name}:${artifact.sha256}`).join("|")}`;
  return <ViewerErrorBoundary resetKey={resetKey}><CadViewportContent {...props} /></ViewerErrorBoundary>;
}

function CadViewportContent({
  projectId,
  units,
  artifacts,
  preferences,
  theme,
  denseMesh = false,
  sourceProxyActive = false,
  hiddenPatchIds = NO_HIDDEN_PATCH_IDS,
  selectedPatchId,
  hoveredPatchId = null,
  grid = false,
  onPreferences,
  onSelectPatch,
  onHoverPatch,
  chrome = "full",
}: CadViewportProps) {
  // Parsed geometry is cached for as long as the project is open rather than
  // being dropped whenever a layer remounts. Superseded artifacts leave the
  // cache as they leave this list; the whole project's entries go when the
  // viewport does.
  const geometryUrls = useMemo(
    () => geometryArtifactUrls(artifacts, (name, sha256) => apiClient.artifactUrl(projectId, name, sha256)),
    [artifacts, projectId],
  );
  useEffect(() => { syncProjectGltfCache(projectId, geometryUrls); }, [geometryUrls, projectId]);
  useEffect(() => () => { releaseProjectGltfCache(projectId); }, [projectId]);

  const [boundsState, setBoundsState] = useState<{ artifactKey: string; box: THREE.Box3 } | null>(null);
  const [command, setCommand] = useState<CameraCommand>({ fitRevision: 0, viewRevision: 0, preset: "iso", direction: null });
  const [selectionState, setSelectionState] = useState<{ sha256: string; ranges: SelectionRange[] } | null>(null);
  const [sectionEnabled, setSectionEnabled] = useState(false);
  const [sectionDirection, setSectionDirection] = useState<"x" | "y" | "z" | "view">("z");
  const [viewSectionNormal, setViewSectionNormal] = useState(() => new THREE.Vector3(0, 0, -1));
  const [sectionPosition, setSectionPosition] = useState(0);
  const [sectionFlipped, setSectionFlipped] = useState(false);
  const [measurementMode, setMeasurementMode] = useState<MeasurementMode | null>(null);
  const [measurementPoints, setMeasurementPoints] = useState<THREE.Vector3[]>([]);
  const [scaleBar, setScaleBar] = useState<ScaleBarSpec | null>(null);
  // Artifacts can be present for a while before the viewer has actually drawn
  // them: the first frame carrying a new material compiles its shaders, which
  // blocks the main thread. Until that frame is on screen the canvas has
  // nothing to show, so the reveal is held behind a stated "preparing" state
  // rather than an empty viewport that looks finished.
  //
  // Only the first paint of a project is held. Later redraws — a display mode,
  // a shading change — leave the previous frame on the canvas, and covering
  // that with a placeholder would replace useful context with less.
  const [paintedProject, setPaintedProject] = useState<string | null>(null);
  const [contextLost, setContextLost] = useState(false);
  const [rendererRevision, setRendererRevision] = useState(0);
  const recoveryTimer = useRef<number | null>(null);
  const handleContextLost = useCallback(() => {
    setContextLost(true);
    if (recoveryTimer.current !== null) window.clearTimeout(recoveryTimer.current);
    recoveryTimer.current = window.setTimeout(() => {
      recoveryTimer.current = null;
      setRendererRevision((revision) => revision + 1);
      setContextLost(false);
    }, 250);
  }, []);
  const handleContextRestored = useCallback(() => {
    if (recoveryTimer.current !== null) window.clearTimeout(recoveryTimer.current);
    recoveryTimer.current = null;
    setContextLost(false);
  }, []);
  useEffect(() => () => {
    if (recoveryTimer.current !== null) window.clearTimeout(recoveryTimer.current);
  }, []);
  const controls = useRef<OrbitControlsImpl | null>(null);
  const viewerCamera = useRef<THREE.Camera | null>(null);
  const palette = viewerPalette(theme);
  const artifactMap = useMemo(() => new Map(artifacts.map((artifact) => [artifact.name, artifact])), [artifacts]);
  const selectionArtifact = artifactMap.get("selection-map.json");
  useEffect(() => {
    if (canShow(preferences.mode, artifactMap)) return;
    const fallback = VIEWER_MODE_FALLBACK_ORDER.find((mode) => canShow(mode, artifactMap));
    if (fallback !== undefined) onPreferences({ mode: fallback });
  }, [artifactMap, onPreferences, preferences.mode]);

  useEffect(() => {
    if (selectionArtifact === undefined) return;
    const controller = new AbortController();
    void Promise.resolve().then(() => apiFetch(
      apiClient.artifactUrl(projectId, selectionArtifact.name, selectionArtifact.sha256),
      { signal: controller.signal },
    ))
      .then((response) => {
        if (!response.ok) throw new Error("selection map unavailable");
        return response.json();
      })
      .then((data: unknown) => {
        if (!isSelectionMap(data)) return;
        const patchGlb = artifactMap.get("patches.glb");
        setSelectionState({
          sha256: selectionArtifact.sha256,
          ranges: patchGlb !== undefined && data.artifact.sha256 === patchGlb.sha256 ? data.ranges : [],
        });
      })
      .catch(() => setSelectionState({ sha256: selectionArtifact.sha256, ranges: [] }));
    return () => controller.abort();
  }, [artifactMap, projectId, selectionArtifact]);

  const layers = layersForMode(preferences, artifactMap);
  const artifactKey = layers.map((layer) => layer.artifact.sha256).join("|") || projectId;
  const preparing = layers.length > 0 && paintedProject !== projectId;
  // A dropped or paused render loop must not strand the viewer behind the
  // overlay; show whatever the canvas has after this long regardless.
  useEffect(() => {
    if (!preparing) return;
    const failsafe = window.setTimeout(() => setPaintedProject(projectId), REVEAL_FAILSAFE_MS);
    return () => window.clearTimeout(failsafe);
  }, [preparing, projectId]);
  const bounds = boundsState?.artifactKey === artifactKey ? boundsState.box : null;
  const selection = selectionArtifact !== undefined
    && selectionState?.sha256 === selectionArtifact.sha256
    ? selectionState.ranges
    : [];
  const sectionNormal = useMemo(() => {
    const normal = sectionDirection === "view"
      ? viewSectionNormal.clone()
      : new THREE.Vector3(
        sectionDirection === "x" ? -1 : 0,
        sectionDirection === "y" ? -1 : 0,
        sectionDirection === "z" ? -1 : 0,
      );
    return sectionFlipped ? normal.multiplyScalar(-1) : normal;
  }, [sectionDirection, sectionFlipped, viewSectionNormal]);
  const sectionPlane = useMemo(
    () => sectionEnabled && bounds !== null
      ? sectionPlaneForBounds(bounds, sectionNormal, sectionPosition)
      : null,
    [bounds, sectionEnabled, sectionNormal, sectionPosition],
  );
  const measurementText = useMemo(() => measurementMode === null
    ? null
    : measurementLabel(
      measurementMode,
      measurementPoints.map((point): Point3 => [point.x, point.y, point.z]),
      units,
    ), [measurementMode, measurementPoints, units]);
  const onScaleChange = useCallback((pxPerUnit: number) => {
    const next = scaleBarForPixelsPerUnit(pxPerUnit);
    if (next === null) return;
    setScaleBar((current) => current !== null && current.value === next.value && current.width === next.width
      ? current
      : next);
  }, []);
  const onBounds = useCallback((box: THREE.Box3) => {
    setBoundsState((current) => {
      const currentBox = current?.artifactKey === artifactKey ? current.box : null;
      const next = currentBox?.clone().union(box) ?? box.clone();
      return currentBox !== null && currentBox.min.equals(next.min) && currentBox.max.equals(next.max)
        ? current
        : { artifactKey, box: next };
    });
  }, [artifactKey]);
  useEffect(() => {
    const fit = () => setCommand((current) => ({ ...current, fitRevision: current.fitRevision + 1 }));
    const view = (event: Event) => {
      const detail = (event as CustomEvent<ViewPreset>).detail;
      if (detail) setCommand((current) => ({ ...current, preset: detail, direction: null, viewRevision: current.viewRevision + 1 }));
    };
    window.addEventListener("mesh2param:fit-view", fit);
    window.addEventListener("mesh2param:view-preset", view);
    return () => {
      window.removeEventListener("mesh2param:fit-view", fit);
      window.removeEventListener("mesh2param:view-preset", view);
    };
  }, []);

  function preset(value: ViewPreset) {
    setCommand((current) => ({ ...current, preset: value, direction: null, viewRevision: current.viewRevision + 1 }));
  }

  function gizmoView(view: GizmoViewRequest) {
    // The gizmo "home" sphere shares the default/reset iso orientation (cameraMath DIRECTIONS.iso).
    if (view === "iso") {
      setCommand((current) => ({ ...current, preset: "iso", direction: null, viewRevision: current.viewRevision + 1 }));
      return;
    }
    const direction: [number, number, number] = typeof view === "object"
      ? view.direction
      : view === "x" ? [1, 0, 0]
      : view === "y" ? [0, 1, 0]
      : view === "z" ? [0, 0, 1]
      : [1, 1, 1];
    setCommand((current) => ({ ...current, direction, viewRevision: current.viewRevision + 1 }));
  }

  function captureViewSectionNormal() {
    const camera = viewerCamera.current;
    if (camera !== null) setViewSectionNormal(camera.getWorldDirection(new THREE.Vector3()).normalize());
  }

  function setMeasureMode(mode: MeasurementMode | null) {
    setMeasurementMode(mode);
    setMeasurementPoints([]);
  }

  return (
    <section
      className="cad-viewport"
      aria-label="3D CAD viewer"
      data-testid="cad-viewport"
      data-camera-view={command.direction?.join(",") ?? command.preset}
      data-display-mode={preferences.shading}
      data-hidden-patch-count={hiddenPatchIds.length}
      data-viewer-preparing={String(preparing)}
      data-grid={String(grid)}
    >
      {chrome === "full" ? (
      <div className="viewport-modebar" role="toolbar" aria-label="Viewer display modes">
        {MODES.map((mode) => (
          <button
            key={mode.id}
            aria-pressed={preferences.mode === mode.id}
            disabled={!canShow(mode.id, artifactMap)}
            title={sourceProxyActive && mode.id === "reconstructed"
              ? "Preserved source facets used as the 3D proxy; the STEP is validated separately."
              : undefined}
            onClick={() => onPreferences({ mode: mode.id })}
          >
            <ModeIcon mode={mode.id} />
            <span>{sourceProxyActive && mode.id === "reconstructed" ? "Converted" : mode.label}</span>
          </button>
        ))}
        <span className="toolbar-separator" />
        <button
          aria-pressed={preferences.edges}
          onClick={() => onPreferences({ edges: !preferences.edges })}
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
          <span>{sourceProxyActive ? "Converted" : "Result"}</span>
          <input
            aria-label={sourceProxyActive ? "Converted model opacity" : "Result opacity"}
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={preferences.resultOpacity}
            onChange={(event) => onPreferences({ resultOpacity: Number(event.currentTarget.value) })}
          />
        </label>
      </div>
      ) : null}

      <div className={`viewport-cad-tools viewport-cad-tools-${chrome}`} aria-label="Section and measurement tools">
        <div className="viewport-tool-row">
          <button
            aria-pressed={sectionEnabled}
            onClick={() => setSectionEnabled((enabled) => !enabled)}
            title="Clip the model with a movable plane"
          ><Slice /><span>Section</span></button>
          <button
            aria-pressed={measurementMode !== null}
            onClick={() => setMeasureMode(measurementMode === null ? "distance" : null)}
            title="Measure distance, angle, or radius from picked points"
          ><Ruler /><span>Measure</span></button>
        </div>
        {sectionEnabled ? (
          <div className="viewport-tool-options" data-testid="section-controls">
            <label>Normal
              <select
                aria-label="Section plane normal"
                value={sectionDirection}
                onChange={(event) => {
                  const direction = event.currentTarget.value as "x" | "y" | "z" | "view";
                  setSectionDirection(direction);
                  if (direction === "view") captureViewSectionNormal();
                }}
              >
                <option value="x">X</option><option value="y">Y</option><option value="z">Z</option>
                <option value="view">Current view</option>
              </select>
            </label>
            <label>Position
              <input
                aria-label="Section plane position"
                type="range"
                min="-1"
                max="1"
                step="0.01"
                value={sectionPosition}
                onChange={(event) => setSectionPosition(Number(event.currentTarget.value))}
              />
            </label>
            <button onClick={() => setSectionFlipped((flipped) => !flipped)}>Flip</button>
            {sectionDirection === "view" ? <button onClick={captureViewSectionNormal}>Use view</button> : null}
          </div>
        ) : null}
        {measurementMode !== null ? (
          <div className="viewport-tool-options" data-testid="measurement-controls">
            <label>Type
              <select
                aria-label="Measurement type"
                value={measurementMode}
                onChange={(event) => setMeasureMode(event.currentTarget.value as MeasurementMode)}
              >
                <option value="distance">Distance</option>
                <option value="angle">Angle</option>
                <option value="radius">Radius (3 points)</option>
              </select>
            </label>
            <span>{measurementPoints.length}/{requiredMeasurementPoints(measurementMode)} points</span>
            <button onClick={() => setMeasurementPoints([])}>Clear</button>
          </div>
        ) : null}
      </div>

      <ViewerErrorBoundary resetKey={artifactKey}>
        <Canvas
          key={`webgl-${rendererRevision}`}
          frameloop="always"
          dpr={viewerDpr(denseMesh)}
          gl={{ alpha: false, antialias: true, powerPreference: "high-performance", preserveDrawingBuffer: false }}
          camera={{ position: [90, -110, 85], up: [0, 0, 1], fov: 42, near: 0.01, far: 100_000 }}
          onPointerMissed={() => onSelectPatch(null)}
          onCreated={({ gl }) => {
            gl.localClippingEnabled = true;
            // three.js validates every freshly linked program with
            // getProgramInfoLog, which blocks the main thread until the driver
            // has finished linking. On a GPU that advertises
            // KHR_parallel_shader_compile this costs little, but on the
            // software fallback (no such extension — older machines, blocklisted
            // GPUs, VMs, remote sessions) it measured ~240ms of the reload.
            // Dev keeps the check so shader authoring errors stay loud;
            // production ships shaders already known to compile.
            gl.debug.checkShaderErrors = import.meta.env.DEV;
          }}
        >
          <color key={palette.background} attach="background" args={[palette.background]} />
          <ambientLight intensity={palette.ambientIntensity} />
          <directionalLight position={[80, -60, 100]} intensity={palette.keyIntensity} />
          <directionalLight position={[-70, 80, 30]} intensity={palette.fillIntensity} />
          <axesHelper args={[35]} />
          {grid && bounds !== null ? <GridFloor bounds={bounds} palette={palette} /> : null}
          <ProjectionController projection={preferences.projection} controlsRef={controls} />
          <ViewerCameraReference targetRef={viewerCamera} />
          <WebGLContextMonitor onLost={handleContextLost} onRestored={handleContextRestored} />
          <Suspense fallback={<Html center className="viewer-loading">Loading geometry…</Html>}>
            {preparing ? <FramePainted onPainted={() => setPaintedProject(projectId)} /> : null}
            {layers.map((layer) => (
              <ArtifactLayer
                key={`${layer.artifact.sha256}-${layer.opacity}-${preferences.shading}-${preferences.edges}-${theme}`}
                url={apiClient.artifactUrl(projectId, layer.artifact.name, layer.artifact.sha256)}
                mode={layer.mode}
                opacity={layer.opacity}
                shading={layer.mode === "patches" ? "wireframe" : preferences.shading}
                edges={preferences.edges}
                comparisonGhost={preferences.mode === "overlay" && layer.mode === "source"}
                facetedProxy={sourceProxyActive && layer.mode === "reconstructed"}
                theme={theme}
                selectionRanges={layer.mode === "patches" ? selection : NO_SELECTION_RANGES}
                hiddenPatchIds={layer.mode === "patches" ? hiddenPatchIds : NO_HIDDEN_PATCH_IDS}
                selectedPatchId={selectedPatchId}
                hoveredPatchId={layer.mode === "patches" ? hoveredPatchId : null}
                sectionPlane={sectionPlane}
                measurementEnabled={measurementMode !== null}
                onBounds={onBounds}
                onMeasurePoint={(point) => setMeasurementPoints((current) => {
                  if (measurementMode === null) return current;
                  const required = requiredMeasurementPoints(measurementMode);
                  return current.length >= required ? [point] : [...current, point];
                })}
                {...(layer.mode === "patches" ? { onSelectPatch } : {})}
                {...(layer.mode === "patches" && onHoverPatch !== undefined ? { onHoverPatch } : {})}
              />
            ))}
            {measurementPoints.map((point, index) => (
              <mesh key={`${index}-${point.x}-${point.y}-${point.z}`} position={point}>
                <sphereGeometry args={[0.8, 16, 12]} /><meshBasicMaterial color={palette.highlight} depthTest={false} />
              </mesh>
            ))}
            {measurementMode === "distance" && measurementPoints.length === 2 ? (
              <>
                <Line points={measurementPoints} color={palette.highlight} lineWidth={2} depthTest={false} />
                <Html position={measurementPoints[0]!.clone().lerp(measurementPoints[1]!, 0.5)} center className="dimension-label">
                  {measurementText}
                </Html>
              </>
            ) : null}
            {measurementMode !== null && measurementMode !== "distance" && measurementPoints.length === 3 ? (
              <>
                <Line
                  points={measurementMode === "angle"
                    ? [measurementPoints[0]!, measurementPoints[1]!, measurementPoints[2]!]
                    : [...measurementPoints, measurementPoints[0]!]}
                  color={palette.highlight}
                  lineWidth={2}
                  depthTest={false}
                />
                <Html
                  position={measurementPoints.reduce(
                    (total, point) => total.add(point),
                    new THREE.Vector3(),
                  ).multiplyScalar(1 / 3)}
                  center
                  className="dimension-label"
                >
                  {measurementText}
                </Html>
              </>
            ) : null}
          </Suspense>
          <CameraRig bounds={bounds} artifactKey={artifactKey} command={command} controlsRef={controls} />
          <ScaleProbe controlsRef={controls} onScale={onScaleChange} />
        </Canvas>
      </ViewerErrorBoundary>

      <OrientationGizmoCanvas cameraRef={viewerCamera} onSelectView={gizmoView} theme={theme} />

      {preparing ? (
        <div className="viewer-preparing" role="status" aria-live="polite">
          <LoaderCircle className="spin" size={18} />
          <strong>Preparing the 3D preview…</strong>
        </div>
      ) : null}

      {contextLost ? (
        <div className="viewer-recovering" role="status" aria-live="polite">
          <strong>Recovering 3D viewer…</strong>
          <span>The model will remain available when the graphics context is restored.</span>
        </div>
      ) : null}

      {layers.length === 0 && chrome === "full" ? (
        <div className="viewer-empty"><Box /><strong>No geometry yet</strong><p>Open a mesh or a sample to begin.</p></div>
      ) : null}
      {scaleBar === null ? null : (
        <div className="scale-bar" aria-hidden="true" data-scale-value={scaleBar.value}>
          <span className="scale-bar-rule" style={{ width: scaleBar.width }} />
          <span className="scale-bar-label">{scaleBar.value} {units}</span>
        </div>
      )}
      {selectedPatchId === null ? null : (
        <div className="selection-chip">Selected patch <strong>{selectedPatchId}</strong></div>
      )}
    </section>
  );
}

/**
 * Reference grid on the model's floor: the plane z = min(bounds), sized to
 * the footprint with a decimal step picked the way the scale bar picks its
 * length, so grid cells and the scale bar read in the same units.
 */
export function gridFloorSpec(bounds: THREE.Box3): { size: number; divisions: number; step: number; z: number } {
  const extent = Math.max(bounds.max.x - bounds.min.x, bounds.max.y - bounds.min.y, 1e-3);
  const raw = extent / 10;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10]
    .map((candidate) => Number((candidate * pow).toPrecision(12)))
    .reduce((best, candidate) => (Math.abs(candidate - raw) < Math.abs(best - raw) ? candidate : best));
  const divisions = Math.max(2, Math.ceil((extent * 2.4) / step));
  return { size: divisions * step, divisions, step, z: bounds.min.z - step * 0.02 };
}

function GridFloor({ bounds, palette }: { bounds: THREE.Box3; palette: ReturnType<typeof viewerPalette> }) {
  const spec = useMemo(() => gridFloorSpec(bounds), [bounds]);
  const center = useMemo(() => bounds.getCenter(new THREE.Vector3()), [bounds]);
  const grid = useMemo(() => {
    const helper = new THREE.GridHelper(spec.size, spec.divisions, palette.gridMajor, palette.gridMinor);
    // GridHelper lies in XZ; the viewer's up axis is +Z.
    helper.rotation.x = Math.PI / 2;
    const material = helper.material as THREE.Material;
    material.transparent = true;
    material.opacity = palette.gridOpacity;
    material.depthWrite = false;
    helper.raycast = () => {};
    helper.renderOrder = -1;
    return helper;
  }, [palette, spec]);
  useEffect(() => () => {
    grid.geometry.dispose();
    (grid.material as THREE.Material).dispose();
  }, [grid]);
  return <primitive object={grid} position={[center.x, center.y, spec.z]} />;
}

function ViewerCameraReference({ targetRef }: { targetRef: MutableRefObject<THREE.Camera | null> }) {
  const { camera } = useThree();
  useEffect(() => {
    targetRef.current = camera;
    return () => {
      if (targetRef.current === camera) targetRef.current = null;
    };
  }, [camera, targetRef]);
  return null;
}

function WebGLContextMonitor({ onLost, onRestored }: { onLost(): void; onRestored(): void }) {
  const { gl, invalidate } = useThree();
  useEffect(() => {
    const canvas = gl.domElement;
    const handleLost = (event: Event) => {
      event.preventDefault();
      debugLog.debug("viewer", "WebGL context lost; remounting renderer");
      onLost();
    };
    const handleRestored = () => {
      debugLog.info("viewer", "WebGL context restored");
      onRestored();
      invalidate();
    };
    canvas.addEventListener("webglcontextlost", handleLost);
    canvas.addEventListener("webglcontextrestored", handleRestored);
    return () => {
      canvas.removeEventListener("webglcontextlost", handleLost);
      canvas.removeEventListener("webglcontextrestored", handleRestored);
    };
  }, [gl, invalidate, onLost, onRestored]);
  return null;
}

/** Reports screen pixels per world unit (measured at the orbit target) whenever a frame renders. */
function ScaleProbe({
  controlsRef,
  onScale,
}: {
  controlsRef: MutableRefObject<OrbitControlsImpl | null>;
  onScale(pxPerUnit: number): void;
}) {
  const { camera, size } = useThree();
  useFrame(() => {
    if (camera instanceof THREE.OrthographicCamera) {
      onScale(camera.zoom);
      return;
    }
    if (!(camera instanceof THREE.PerspectiveCamera)) return;
    const target = controlsRef.current?.target;
    const distance = Math.max(target === undefined ? camera.position.length() : camera.position.distanceTo(target), 1e-6);
    const worldHeight = 2 * distance * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    onScale(size.height / worldHeight);
  });
  return null;
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
  if (mode === "overlay") {
    return [
      { name: "source.glb", opacity: preferences.sourceOpacity, mode: "source" },
      { name: "reconstructed.glb", opacity: preferences.resultOpacity, mode: "reconstructed" },
    ].flatMap((item) => {
      const artifact = map.get(item.name);
      return artifact === undefined ? [] : [{ artifact, opacity: item.opacity, mode: item.mode }];
    });
  }
  const artifact = map.get(MODE_GEOMETRY[mode] ?? "");
  const opacity = mode === "source" ? preferences.sourceOpacity : preferences.resultOpacity;
  return artifact === undefined ? [] : [{ artifact, opacity, mode }];
}

function canShow(mode: ViewerMode, map: Map<string, ArtifactDescriptor>): boolean {
  if (mode === "overlay") return OVERLAY_GEOMETRY.every((name) => map.has(name));
  return map.has(MODE_GEOMETRY[mode] ?? "");
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

class ViewerErrorBoundary extends Component<{ children: ReactNode; resetKey: string }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(error: unknown) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
  componentDidUpdate(previous: Readonly<{ children: ReactNode; resetKey: string }>) {
    if (previous.resetKey !== this.props.resetKey && this.state.error !== null) {
      this.setState({ error: null });
    }
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    debugLog.error("viewer", `Geometry render failed: ${error.message}`, info.componentStack ?? undefined);
  }
  render() {
    return this.state.error === null ? this.props.children : (
      <div className="viewer-error" role="alert">
        <strong>Viewer could not load geometry</strong><span>{this.state.error}</span>
      </div>
    );
  }
}
