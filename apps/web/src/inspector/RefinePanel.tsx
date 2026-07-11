import { useEffect, useMemo, useState } from "react";
import { Copy, Eye, EyeOff, Lock, Play, Trash2 } from "lucide-react";
import { Button, NumberField, PanelSection } from "@mesh2param/ui";
import type { Feature } from "@mesh2param/contracts";
import type { WorkspaceActions, WorkspaceViewModel } from "../workspace/types";
import { InspectorFrame } from "../workspace/InspectorFrame";
import { JobProgress, TechnicalRows } from "./shared";
import { FeatureList } from "./FeaturesPanel";

interface ParameterField {
  key: string;
  label: string;
  unit: string;
  integer?: boolean;
}

export function RefinePanel({ vm, actions }: { vm: WorkspaceViewModel; actions: WorkspaceActions }) {
  const graph = vm.project.state.cadgraph;
  const features = graph?.features ?? [];
  const selected = features.find((feature) => feature.id === vm.selectedFeatureId) ?? features[0] ?? null;
  const fields = useMemo(() => selected === null ? [] : parameterFields(selected, vm.project.units), [selected, vm.project.units]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [editError, setEditError] = useState<string | null>(null);

  useEffect(() => {
    if (selected === null) { setValues({}); return; }
    const record = selected as unknown as Record<string, unknown>;
    setValues(Object.fromEntries(fields.map((field) => [field.key, String(record[field.key] ?? "")])));
    setEditError(null);
  }, [fields, selected]);

  async function commitParameter(field: ParameterField) {
    if (graph === null || selected === null || !vm.serverWritable) return;
    const raw = Number(values[field.key]);
    const value = field.integer ? Math.round(raw) : raw;
    if (!Number.isFinite(value) || value <= 0 || (field.integer && value < 2)) {
      setEditError(`${field.label} must be ${field.integer ? "an integer of at least 2" : "a positive finite value"}.`);
      return;
    }
    const next = structuredClone(graph);
    const feature = next.features.find((item) => item.id === selected.id);
    if (feature === undefined) return;
    (feature as unknown as Record<string, unknown>)[field.key] = value;
    try {
      await actions.updateCadgraph(next, `Edit ${selected.name} ${field.label.toLowerCase()}`);
      setValues((current) => ({ ...current, [field.key]: String(value) }));
      setEditError(null);
    } catch (cause) {
      setEditError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  async function toggleSuppressed() {
    if (graph === null || selected === null) return;
    const next = structuredClone(graph);
    const feature = next.features.find((item) => item.id === selected.id);
    if (feature === undefined) return;
    feature.suppressed = !feature.suppressed;
    await actions.updateCadgraph(next, feature.suppressed ? "Suppress feature" : "Unsuppress feature");
    await actions.run("rebuild");
  }

  return (
    <InspectorFrame step="refine" title="Refine" helper="Edit parameters while preserving the last kernel-valid geometry." onStep={actions.setStep}>
      {vm.activeJob?.job.kind === "rebuild" ? <JobProgress state={vm.activeJob} onCancel={() => void actions.cancelJob()} /> : null}
      <PanelSection title="Feature tree"><FeatureList features={features} selected={selected?.id ?? null} onSelect={actions.selectFeature} /></PanelSection>
      {selected === null ? null : (
        <PanelSection title={selected.name}>
          <TechnicalRows rows={[
            ["Operation", selected.operation],
            ["Order", selected.order],
            ["Confidence", `${Math.round(selected.confidence * 100)}%`],
            ["Evidence", selected.sourceEvidence.length],
            ["State", selected.suppressed ? "Suppressed" : "Active"],
          ]} />
          {fields.map((field) => (
            <NumberField
              key={field.key}
              label={field.label}
              unit={field.unit}
              value={values[field.key] ?? ""}
              min={field.integer ? "2" : "0.000001"}
              step={field.integer ? "1" : "0.1"}
              readOnly={!vm.serverWritable}
              onChange={(event) => {
                const nextValue = event.currentTarget.value;
                setValues((current) => ({ ...current, [field.key]: nextValue }));
              }}
              onBlur={() => void commitParameter(field)}
              onKeyDown={(event) => { if (event.key === "Enter") void commitParameter(field); }}
            />
          ))}
          {fields.length === 0 ? <p className="panel-note">This operation has no directly editable scalar parameter.</p> : null}
          {editError === null ? null : <p className="inline-error" role="alert"><strong>Parameter not saved</strong>{editError}</p>}
          <div className="button-grid">
            <Button disabled={!vm.workerReady || !vm.serverWritable} onClick={() => void toggleSuppressed()}>{selected.suppressed ? <Eye /> : <EyeOff />}{selected.suppressed ? "Unsuppress" : "Suppress"}</Button>
            <Button disabled title="Feature lock editing is planned for the next milestone."><Lock />Lock</Button>
            <Button disabled title="Feature duplication needs semantic-topology remapping and is not available yet."><Copy />Duplicate</Button>
            <Button disabled title="Feature deletion needs dependency repair and is not available yet."><Trash2 />Delete</Button>
          </div>
        </PanelSection>
      )}
      <div className="panel-actions"><Button variant="primary" onClick={() => void actions.run("rebuild")} disabled={!vm.workerReady || !vm.serverWritable || !graph || Boolean(vm.activeJob)}><Play size={16} />Rebuild</Button></div>
    </InspectorFrame>
  );
}

function parameterFields(feature: Feature, units: string): ParameterField[] {
  switch (feature.operation) {
    case "extrusion": return "distance" in feature ? [{ key: "distance", label: "Distance", unit: units }] : [];
    case "pocket": return [{ key: "depth", label: "Depth", unit: units }];
    case "hole": return [
      { key: "diameter", label: "Diameter", unit: units },
      ...("depth" in feature && typeof feature.depth === "number" && Number.isFinite(feature.depth)
        ? [{ key: "depth", label: "Depth", unit: units }]
        : []),
    ];
    case "counterbore": return [{ key: "diameter", label: "Diameter", unit: units }, { key: "boreDiameter", label: "Bore diameter", unit: units }, { key: "boreDepth", label: "Bore depth", unit: units }];
    case "countersink": return [{ key: "diameter", label: "Diameter", unit: units }, { key: "sinkDiameter", label: "Sink diameter", unit: units }, { key: "sinkAngleDeg", label: "Sink angle", unit: "°" }];
    case "revolution": return [{ key: "angleDeg", label: "Angle", unit: "°" }];
    case "linearPattern": return [{ key: "count", label: "Count", unit: "", integer: true }, { key: "spacing", label: "Spacing", unit: units }];
    case "circularPattern": return [{ key: "count", label: "Count", unit: "", integer: true }, { key: "totalAngleDeg", label: "Total angle", unit: "°" }];
    case "chamfer": return [{ key: "width", label: "Width", unit: units }];
    case "fillet": return [{ key: "radius", label: "Radius", unit: units }];
    default: return [];
  }
}
