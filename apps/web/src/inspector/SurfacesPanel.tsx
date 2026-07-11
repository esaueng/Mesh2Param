import { Eye, EyeOff, Lock, Merge, Search, Unlock } from "lucide-react";
import { Button, NumberField, PanelSection, SelectField } from "@mesh2param/ui";
import { useEffect, useMemo, useState } from "react";
import type { SurfacePatch } from "../state/types";
import type { WorkspaceActions, WorkspaceViewModel } from "../workspace/types";
import { InspectorFrame } from "../workspace/InspectorFrame";
import { JobProgress, TechnicalRows } from "./shared";

const CLASSIFICATIONS: SurfacePatch["type"][] = ["plane", "cylinder", "cone", "sphere", "freeform", "unknown"];

export function SurfacesPanel({ vm, actions }: { vm: WorkspaceViewModel; actions: WorkspaceActions }) {
  const [query, setQuery] = useState("");
  const [maxDeviation, setMaxDeviation] = useState(0.05);
  const [minPatchArea, setMinPatchArea] = useState(5);
  const [maxAngle, setMaxAngle] = useState(10);
  const patches = useMemo(() => vm.project.state.patches.filter((patch) =>
    (patch.name ?? patch.id).toLowerCase().includes(query.toLowerCase())
    || patch.type.includes(query.toLowerCase())), [query, vm.project.state.patches]);
  const selected = vm.project.state.patches.find((patch) => patch.id === vm.selectedPatchId) ?? null;
  const [classification, setClassification] = useState<SurfacePatch["type"]>("unknown");
  useEffect(() => {
    if (selected !== null) setClassification(selected.type);
  }, [selected]);
  const mergeNeighbor = selected?.neighborIds?.find((id) => vm.project.state.patches.some((patch) => patch.id === id));

  return (
    <InspectorFrame
      step="surfaces"
      title="Surfaces"
      helper="Review and edit analytic surfaces fitted to the repaired mesh."
      onStep={actions.setStep}
    >
      {vm.activeJob?.job.kind === "analyze"
        ? <JobProgress state={vm.activeJob} onCancel={() => void actions.cancelJob()} />
        : null}
      <PanelSection title="Segmentation tolerance">
        <NumberField label="Max deviation" unit="mm" value={maxDeviation} min="0.000001" step="0.001" onChange={(event) => setMaxDeviation(Number(event.currentTarget.value))} />
        <NumberField label="Min patch area" unit="mm²" value={minPatchArea} min="0" step="0.1" onChange={(event) => setMinPatchArea(Number(event.currentTarget.value))} />
        <NumberField label="Max angle" unit="°" value={maxAngle} min="0.001" max="89.999" step="0.5" onChange={(event) => setMaxAngle(Number(event.currentTarget.value))} />
        <Button onClick={() => void actions.run("analyze", { maxDeviation, minPatchArea, maxAngleDeg: maxAngle })} disabled={!vm.workerReady || !vm.serverWritable || Boolean(vm.activeJob)}>Re-run analysis</Button>
      </PanelSection>
      <div className="search-field"><Search size={14} /><input aria-label="Search patches" placeholder="Search patches…" value={query} onChange={(event) => setQuery(event.currentTarget.value)} /></div>
      <div className="patch-table" role="table" aria-label="Fitted surfaces">
        <div className="patch-row header" role="row"><span>#</span><span>Type / name</span><span>RMS</span><span>State</span></div>
        {patches.map((patch, index) => (
          <button
            role="row"
            key={patch.id}
            data-patch-id={patch.id}
            data-patch-type={patch.type}
            aria-selected={patch.id === vm.selectedPatchId}
            className={`patch-row ${patch.id === vm.selectedPatchId ? "selected" : ""}`}
            onClick={() => actions.selectPatch(patch.id)}
          >
            <span>{index + 1}</span>
            <span><strong>{patch.type}</strong><small>{patch.name ?? patch.id.slice(0, 16)}</small></span>
            <span>{patch.residualsMm?.rms.toFixed(4) ?? "—"}</span>
            <span>{patch.locked ? <Lock /> : patch.hidden ? <EyeOff /> : <Eye />}</span>
          </button>
        ))}
      </div>
      {selected === null ? null : (
        <PanelSection title={selected.name ?? selected.id}>
          <TechnicalRows rows={[
            ["Type", selected.type],
            ["Area", selected.areaMm2 ? `${selected.areaMm2.toFixed(2)} mm²` : null],
            ["Confidence", selected.confidence ? `${Math.round(selected.confidence * 100)}%` : null],
            ["RMS", selected.residualsMm ? `${selected.residualsMm.rms.toFixed(5)} mm` : null],
            ["P95", selected.residualsMm ? `${selected.residualsMm.p95.toFixed(5)} mm` : null],
            ["Triangles", selected.triangleCount?.toLocaleString() ?? "—"],
          ]} />
          <SelectField
            label="Classification"
            value={classification}
            onChange={(event) => setClassification(event.currentTarget.value as SurfacePatch["type"])}
          >
            {CLASSIFICATIONS.map((value) => <option key={value} value={value}>{value}</option>)}
          </SelectField>
          <div className="button-grid">
            <Button disabled={!vm.serverWritable} onClick={() => void actions.updatePatch(selected.id, { hidden: !selected.hidden })}>
              {selected.hidden ? <Eye /> : <EyeOff />}{selected.hidden ? "Show" : "Hide"}
            </Button>
            <Button disabled={!vm.serverWritable} onClick={() => void actions.updatePatch(selected.id, { locked: !selected.locked })}>
              {selected.locked ? <Unlock /> : <Lock />}{selected.locked ? "Unlock" : "Lock"}
            </Button>
            <Button
              onClick={() => void actions.updatePatch(selected.id, { classification })}
              disabled={!vm.serverWritable || classification === selected.type}
            >
              Apply classification
            </Button>
            <Button
              onClick={() => mergeNeighbor === undefined ? undefined : void actions.mergePatches([selected.id, mergeNeighbor])}
              disabled={!vm.serverWritable || mergeNeighbor === undefined}
              title={mergeNeighbor === undefined ? "This patch has no adjacent patch available to merge." : `Merge with ${mergeNeighbor}`}
            >
              <Merge />Merge neighbor
            </Button>
            <Button disabled title="Interactive triangle splitting is planned for the next milestone.">Split · planned</Button>
          </div>
        </PanelSection>
      )}
    </InspectorFrame>
  );
}
