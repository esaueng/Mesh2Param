import { useEffect, useState } from "react";
import { Boxes, Plus, RefreshCw, Sparkles } from "lucide-react";
import { Button, NumberField, PanelSection, SelectField } from "@mesh2param/ui";
import type { CADGraph, Feature } from "@mesh2param/contracts";
import type { WorkspaceActions, WorkspaceViewModel } from "../workspace/types";
import type { CandidateHistory } from "../state/types";
import { apiClient } from "../api/client";
import { InspectorFrame } from "../workspace/InspectorFrame";
import { JobProgress } from "./shared";
import { automaticReconstructionCapability } from "../workspace/automaticReconstruction";
import {
  candidatesFromSettings,
  selectableCandidateGraph,
  selectedCandidateLabel,
} from "./candidateSelection";

type ManualFeatureKind =
  | "extrusion" | "revolution" | "pocket" | "hole" | "counterbore" | "countersink"
  | "linearPattern" | "circularPattern" | "mirror" | "fillet" | "chamfer" | "importedFaceted";

const MILLIMETERS_PER_PROJECT_UNIT = {
  mm: 1,
  cm: 10,
  m: 1_000,
  in: 25.4,
  ft: 304.8,
} as const;

function millimetersPerProjectUnit(units: WorkspaceViewModel["project"]["units"]): number {
  return MILLIMETERS_PER_PROJECT_UNIT[units];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function persistedSewingTolerance(
  graph: CADGraph | null,
  settings: WorkspaceViewModel["project"]["state"]["settings"],
  units: WorkspaceViewModel["project"]["units"],
): number {
  const featureTolerance = graph?.features.find((feature) => feature.operation === "importedFaceted")?.sewingTolerance;
  if (typeof featureTolerance === "number" && Number.isFinite(featureTolerance) && featureTolerance > 0) {
    return featureTolerance;
  }
  const fallback = settings.facetedFallback;
  const settingsTolerance = isRecord(fallback)
    ? fallback.sewingTolerance ?? fallback.sewingToleranceMm
    : undefined;
  return typeof settingsTolerance === "number" && Number.isFinite(settingsTolerance) && settingsTolerance > 0
    ? settingsTolerance
    : 0.05 / millimetersPerProjectUnit(units);
}

export function FeaturesPanel({ vm, actions }: { vm: WorkspaceViewModel; actions: WorkspaceActions }) {
  const graph = vm.project.state.cadgraph;
  const features = graph?.features ?? [];
  const [kind, setKind] = useState<ManualFeatureKind>("hole");
  const [value, setValue] = useState(5);
  const millimetersPerUnit = millimetersPerProjectUnit(vm.project.units);
  const persistedTolerance = persistedSewingTolerance(graph, vm.project.state.settings, vm.project.units);
  const [sewingTolerance, setSewingTolerance] = useState(persistedTolerance);
  const [manualError, setManualError] = useState<string | null>(null);
  const [candidateError, setCandidateError] = useState<string | null>(null);
  const [artifactCandidates, setArtifactCandidates] = useState<CandidateHistory[] | null>(null);
  const candidateArtifact = vm.artifacts.find((artifact) => artifact.name === "candidates.json");
  const persistedCandidates = candidatesFromSettings(vm.project.state.settings.candidateHistories);
  const candidates = artifactCandidates ?? persistedCandidates;
  const selectedCandidate = selectedCandidateLabel(graph, vm.project.state.settings);
  const automaticReconstruction = automaticReconstructionCapability(vm.project.state);
  const sourceIsStl = vm.project.state.source?.format === "stl";
  const sourceTransformSupported = vm.project.state.source?.declaredUnits === vm.project.units
    && vm.project.state.source.scaleFactor === 1;
  const facetedFallbackActive = graph?.extensions?.["mesh2param.dev/facetedFallback"] !== undefined;
  const facetedFallbackRerunnable = Boolean(facetedFallbackActive
    && graph?.features.length === 1
    && graph.features[0]?.operation === "importedFaceted"
    && graph.features[0].booleanMode === "base");
  const editableGraphPreserved = graph !== null && !facetedFallbackRerunnable;
  const fallbackUnavailableReason = !sourceIsStl
    ? "The faceted STEP fallback currently supports STL sources."
    : !sourceTransformSupported
      ? "Re-import with source units matching project units and scale factor 1 before using the faceted fallback."
    : editableGraphPreserved
      ? "Unavailable while an editable CADGraph exists; Mesh2Param will not replace that feature history with a one-feature faceted fallback."
      : undefined;
  const diagnostics = vm.project.state.diagnostics;
  useEffect(() => {
    setSewingTolerance(persistedTolerance);
  }, [persistedTolerance, vm.project.id]);
  useEffect(() => {
    setArtifactCandidates(null);
    if (candidateArtifact === undefined) return;
    const controller = new AbortController();
    void fetch(apiClient.artifactUrl(vm.project.id, candidateArtifact.name, candidateArtifact.sha256), { signal: controller.signal })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("candidate artifact unavailable")))
      .then((value: unknown) => setArtifactCandidates(candidatesFromSettings(value)))
      .catch(() => { if (!controller.signal.aborted) setArtifactCandidates(null); });
    return () => controller.abort();
  }, [candidateArtifact?.name, candidateArtifact?.sha256, vm.project.id]);

  async function addManualFeature() {
    if (graph === null) return;
    setManualError(null);
    try {
      const next = structuredClone(graph);
      next.features.push(makeManualFeature(next, kind, value));
      await actions.updateCadgraph(next, `Add ${kind}`);
      await actions.run("rebuild");
    } catch (cause) {
      setManualError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  async function chooseCandidate(candidate: CandidateHistory) {
    setCandidateError(null);
    try {
      const next = selectableCandidateGraph(candidate);
      await actions.updateCadgraph(next, `Select ${candidate.label} candidate`);
      await actions.run("rebuild");
    } catch (cause) {
      setCandidateError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  return (
    <InspectorFrame
      step="features"
      title="Features"
      helper="Compare candidate histories and inspect evidence behind each inferred feature."
      onStep={actions.setStep}
    >
      {vm.activeJob?.job.kind === "reconstruct"
        ? <JobProgress state={vm.activeJob} onCancel={() => void actions.cancelJob()} />
        : null}
      <PanelSection title="Automatic reconstruction">
        <p className="panel-note">{automaticReconstruction.supported
          ? "Candidate search rejects kernel-invalid solids before scoring geometric fit."
          : automaticReconstruction.reason}</p>
        <Button
          variant="primary"
          onClick={() => void actions.run("reconstruct")}
          title={automaticReconstruction.supported ? undefined : automaticReconstruction.reason}
          disabled={!automaticReconstruction.supported || !vm.workerReady || !vm.serverWritable || !vm.project.state.source || Boolean(vm.activeJob)}
        >
          <Sparkles size={16} />Auto reconstruct
        </Button>
        {!automaticReconstruction.supported && automaticReconstruction.sampleId !== undefined && graph !== null ? (
          <Button
            onClick={() => void actions.run("rebuild")}
            disabled={!vm.workerReady || !vm.serverWritable || Boolean(vm.activeJob)}
          >
            <RefreshCw size={16} />Rebuild sample CADGraph
          </Button>
        ) : null}
      </PanelSection>
      <PanelSection title="Faceted STEP fallback">
        <p className="panel-note">
          Attempt a non-parametric STEP from the preserved STL facets. A successful STEP is independently kernel-validated; when OCCT tessellation is skipped, the unchanged source mesh is explicitly labeled as the 3D proxy.
        </p>
        {diagnostics === null || diagnostics === undefined ? null : (
          <p className="panel-note">
            Source evidence: {diagnostics.connectedComponentCount} component{diagnostics.connectedComponentCount === 1 ? "" : "s"}, {diagnostics.openBoundaryCount} open boundar{diagnostics.openBoundaryCount === 1 ? "y" : "ies"}, {diagnostics.triangleCount.toLocaleString()} triangles.
          </p>
        )}
        <NumberField
          label="Sewing tolerance (project units)"
          unit={vm.project.units}
          value={sewingTolerance}
          min={String(0.000001 / millimetersPerUnit)}
          max={String(10 / millimetersPerUnit)}
          step={String(0.01 / millimetersPerUnit)}
          onChange={(event) => setSewingTolerance(Number(event.currentTarget.value))}
        />
        {facetedFallbackActive ? <p className="panel-note" role="status">Active model includes source-bound faceted geometry. STEP validity is independently checked; no analytic source history or measured mesh deviation is claimed.</p> : null}
        {editableGraphPreserved ? <p className="panel-note" role="status">Existing editable CADGraph preserved. This fallback is disabled because completing it would replace the feature history.</p> : null}
        <Button
          onClick={() => void actions.run("reconstruct", { mode: "faceted", sewingTolerance })}
          title={fallbackUnavailableReason}
          disabled={fallbackUnavailableReason !== undefined || !vm.workerReady || !vm.serverWritable || Boolean(vm.activeJob)}
        >
          <Boxes size={16} />Sew source facets and create STEP
        </Button>
      </PanelSection>
      <PanelSection title="Add feature">
        <SelectField
          label="Operation"
          value={kind}
          onChange={(event) => setKind(event.currentTarget.value as ManualFeatureKind)}
        >
          <option value="extrusion">Extrusion</option>
          <option value="revolution">Revolution</option>
          <option value="pocket">Pocket</option>
          <option value="hole">Hole</option>
          <option value="counterbore">Counterbore</option>
          <option value="countersink">Countersink</option>
          <option value="linearPattern">Linear pattern</option>
          <option value="circularPattern">Circular pattern</option>
          <option value="mirror">Mirror</option>
          <option value="fillet">Fillet</option>
          <option value="chamfer">Chamfer</option>
          <option value="importedFaceted">Imported faceted fallback</option>
        </SelectField>
        <NumberField
          label={kind === "revolution" ? "Angle" : kind === "hole" || kind === "counterbore" || kind === "countersink" ? "Diameter" : kind === "fillet" ? "Radius" : kind === "chamfer" ? "Width" : kind.includes("Pattern") ? "Spacing / count" : kind === "pocket" ? "Depth" : "Distance"}
          unit={kind === "revolution" ? "°" : kind.includes("Pattern") || kind === "mirror" || kind === "importedFaceted" ? "" : vm.project.units}
          value={value}
          min="0.001"
          max={kind === "revolution" ? "360" : undefined}
          step="0.1"
          onChange={(event) => setValue(Number(event.currentTarget.value))}
        />
        <p className="panel-note">Sketch-based operations use the first closed profile; edge operations use the first resolved semantic edge. Missing context is reported without changing the graph.</p>
        {manualError === null ? null : <p className="inline-error" role="alert"><strong>Feature not added</strong>{manualError}</p>}
        <Button onClick={() => void addManualFeature()} disabled={!vm.workerReady || !vm.serverWritable || graph === null || Boolean(vm.activeJob)}>
          <Plus size={15} />Add and rebuild
        </Button>
      </PanelSection>
      <PanelSection title={`Feature tree · ${features.length}`}>
        <FeatureList features={features} selected={vm.selectedFeatureId} onSelect={actions.selectFeature} />
      </PanelSection>
      <PanelSection title={`Candidate histories · ${candidates.length}`}>
        {candidates.length === 0 ? <p className="panel-note">{automaticReconstruction.supported
          ? "Run automatic reconstruction to generate bounded, kernel-checked alternatives."
          : "Automatic candidate histories are unavailable for the current source evidence."}</p> : (
          <div className="version-list candidate-list">
            {candidates.map((candidate) => (
              <button
                type="button"
                key={candidate.label}
                aria-pressed={candidate.label === selectedCandidate}
                onClick={() => void chooseCandidate(candidate)}
                disabled={!candidate.valid || candidate.cadgraph === undefined || !vm.workerReady || !vm.serverWritable || Boolean(vm.activeJob)}
                title={!candidate.valid ? candidate.rejectionReason ?? "Rejected by the CAD kernel" : candidate.cadgraph === undefined ? "This history does not contain an editable CADGraph snapshot." : undefined}
              >
                <span>{candidate.label}{candidate.label === selectedCandidate ? " · selected" : ""}</span>
                <small>{candidate.valid ? "Kernel valid" : "Rejected"} · score {candidate.score.toFixed(4)} · {candidate.featureCount} features</small>
              </button>
            ))}
          </div>
        )}
        {candidateError === null ? null : <p className="inline-error" role="alert"><strong>Candidate not selected</strong>{candidateError}</p>}
        <p className="panel-note">Selecting a valid history replaces the editable CADGraph and rebuilds it through the geometry worker.</p>
      </PanelSection>
      {features.length === 0 ? (
        <div className="empty-state"><Boxes /><strong>No candidate features</strong><p>Analyze surfaces for parametric inference, or use the explicit faceted STEP fallback.</p></div>
      ) : null}
    </InspectorFrame>
  );
}

export function FeatureList({
  features,
  selected,
  onSelect,
}: {
  features: Feature[];
  selected: string | null;
  onSelect(id: string): void;
}) {
  return (
    <div className="feature-list" role="tree" aria-label="Feature tree">
      {features.map((feature, index) => (
        <button
          role="treeitem"
          aria-selected={feature.id === selected}
          data-feature-id={feature.id}
          data-feature-operation={feature.operation}
          className={feature.id === selected ? "selected" : ""}
          key={feature.id}
          onClick={() => onSelect(feature.id)}
        >
          <span>{String(index + 1).padStart(2, "0")}</span>
          <span><strong>{feature.name}</strong><small>{feature.operation === "importedFaceted"
            ? "importedFaceted · source-bound · non-parametric"
            : `${feature.operation} · ${Math.round(feature.confidence * 100)}% confidence`}</small></span>
          {feature.suppressed ? <em>Suppressed</em> : null}
        </button>
      ))}
    </div>
  );
}

function makeManualFeature(graph: CADGraph, kind: ManualFeatureKind, value: number): Feature {
  if (!Number.isFinite(value) || value <= 0) throw new Error("Enter a positive finite parameter.");
  const id = `feature-${crypto.randomUUID()}`;
  const common = {
    id,
    name: `Manual ${kind}`,
    operation: kind,
    order: graph.features.length,
    dependencies: graph.features.length === 0 ? [] : [graph.features.at(-1)!.id],
    suppressed: false,
    sourceEvidence: [],
    confidence: 1,
    userLocks: [],
    overrides: [],
    semanticOutputs: [],
  };
  const sketch = graph.sketches.find((item) => !item.suppressed && item.profiles.length > 0);
  const profileId = sketch?.profiles[0]?.id;
  if (kind === "extrusion" || kind === "pocket" || kind === "revolution") {
    if (sketch === undefined || profileId === undefined) {
      throw new Error(`${kind} requires a closed sketch profile. Reconstruct a sketch before adding this operation.`);
    }
    if (kind === "extrusion") return {
      ...common,
      operation: "extrusion",
      booleanMode: graph.features.length === 0 ? "base" : "additive",
      sketchId: sketch.id,
      profileIds: [profileId],
      direction: { x: 0, y: 0, z: 1 },
      extent: "blind",
      distance: value,
    };
    if (kind === "pocket") return {
      ...common,
      operation: "pocket",
      booleanMode: "subtractive",
      sketchId: sketch.id,
      profileIds: [profileId],
      direction: { x: 0, y: 0, z: -1 },
      extent: "blind",
      depth: value,
    };
    return {
      ...common,
      operation: "revolution",
      booleanMode: graph.features.length === 0 ? "base" : "additive",
      sketchId: sketch.id,
      profileIds: [profileId],
      axis: { origin: { x: 0, y: 0, z: 0 }, direction: { x: 0, y: 0, z: 1 } },
      angleDeg: Math.min(value, 360),
    };
  }
  if (kind === "hole") {
    if (graph.features.length === 0) throw new Error("A hole requires an existing solid feature.");
    return {
      ...common,
      operation: "hole",
      booleanMode: "subtractive",
      holeType: "through",
      position: { x: 0, y: 0, z: 0 },
      axis: { x: 0, y: 0, z: 1 },
      diameter: value,
    };
  }
  if (kind === "counterbore" || kind === "countersink") {
    if (graph.features.length === 0) throw new Error(`A ${kind} requires an existing solid feature.`);
    const holeBase = {
      ...common,
      booleanMode: "subtractive" as const,
      holeType: "through" as const,
      position: { x: 0, y: 0, z: 0 },
      axis: { x: 0, y: 0, z: 1 },
      diameter: value,
    };
    if (kind === "counterbore") return {
      ...holeBase,
      operation: "counterbore",
      boreDiameter: value * 1.75,
      boreDepth: value,
    };
    return {
      ...holeBase,
      operation: "countersink",
      sinkDiameter: value * 1.75,
      sinkAngleDeg: 90,
    };
  }
  if (kind === "linearPattern" || kind === "circularPattern" || kind === "mirror") {
    const sourceFeature = graph.features.at(-1);
    if (sourceFeature === undefined) throw new Error(`${kind} requires an existing source feature.`);
    if (kind === "linearPattern") return {
      ...common,
      operation: "linearPattern",
      sourceFeatureIds: [sourceFeature.id],
      direction: { x: 1, y: 0, z: 0 },
      count: Math.max(2, Math.round(value)),
      spacing: value,
    };
    if (kind === "circularPattern") return {
      ...common,
      operation: "circularPattern",
      sourceFeatureIds: [sourceFeature.id],
      axis: { origin: { x: 0, y: 0, z: 0 }, direction: { x: 0, y: 0, z: 1 } },
      count: Math.max(2, Math.round(value)),
      totalAngleDeg: 360,
    };
    return {
      ...common,
      operation: "mirror",
      sourceFeatureIds: [sourceFeature.id],
      plane: { origin: { x: 0, y: 0, z: 0 }, normal: { x: 1, y: 0, z: 0 }, xAxis: { x: 0, y: 1, z: 0 } },
      keepOriginals: true,
    };
  }
  if (kind === "importedFaceted") {
    if (graph.source == null) throw new Error("Imported fallback requires a preserved source descriptor.");
    return {
      ...common,
      operation: "importedFaceted",
      booleanMode: graph.features.length === 0 ? "base" : "additive",
      sourceArtifactId: "artifact.source",
      meshSha256: graph.source.sha256,
      intent: "fallback",
    };
  }
  const edge = graph.semanticTopology.find((item) => item.kind === "edge" && item.status === "resolved");
  if (edge === undefined) throw new Error(`${kind} requires a resolved semantic edge.`);
  if (kind === "fillet") return { ...common, operation: "fillet", targetEdges: [edge.id], radius: value };
  return { ...common, operation: "chamfer", targetEdges: [edge.id], width: value };
}
