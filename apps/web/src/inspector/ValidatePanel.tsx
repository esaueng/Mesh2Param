import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { Button, NumberField, PanelSection, StatusGlyph } from "@mesh2param/ui";
import type { WorkspaceActions, WorkspaceViewModel } from "../workspace/types";
import { InspectorFrame } from "../workspace/InspectorFrame";
import { JobProgress, TechnicalRows } from "./shared";

export function ValidatePanel({ vm, actions }: { vm: WorkspaceViewModel; actions: WorkspaceActions }) {
  const result = vm.project.state.validation;
  const metrics = vm.project.state.metrics;
  const [tolerance, setTolerance] = useState(vm.project.state.cadgraph?.projectTolerance.surfaceDeviation ?? 0.15);
  useEffect(() => {
    setTolerance(vm.project.state.cadgraph?.projectTolerance.surfaceDeviation ?? 0.15);
  }, [vm.project.state.cadgraph?.projectTolerance.surfaceDeviation]);
  return (
    <InspectorFrame step="validate" title="Validate" helper="Prove B-Rep validity, STEP reimport, and geometric tolerance separately." onStep={actions.setStep}>
      {vm.activeJob?.job.kind === "validate" ? <JobProgress state={vm.activeJob} onCancel={() => void actions.cancelJob()} /> : null}
      <PanelSection title="Tolerance">
        <NumberField label="Surface deviation" unit={vm.project.units} value={tolerance} min="0.000001" step="0.01" onChange={(event) => setTolerance(Number(event.currentTarget.value))} />
      </PanelSection>
      <PanelSection title="Kernel checks">
        <div className="validation-list">
          <div data-validation-stage="brep"><span>B-Rep solid</span><StatusGlyph state={result?.brepValid ? "complete" : result ? "failed" : "idle"} label={result?.brepValid ? "Valid" : "Not validated"} /></div>
          <div data-validation-stage="step-export"><span>STEP export</span><StatusGlyph state={result?.step ? "complete" : "idle"} label={result?.step ? "Exported" : "Not run"} /></div>
          <div data-validation-stage="step-reimport"><span>STEP reimport</span><StatusGlyph state={result?.stepReimportValid ? "complete" : result ? "failed" : "idle"} label={result?.stepReimportValid ? "Successful" : "Not validated"} /></div>
          <div data-validation-stage="comparison"><span>Within tolerance</span><StatusGlyph state={result?.toleranceSatisfied ? "complete" : result?.toleranceSatisfied === false ? "warning" : "idle"} label={result?.toleranceSatisfied ? "Within tolerance" : "Not confirmed"} /></div>
        </div>
      </PanelSection>
      <PanelSection title="Comparison metrics">
        {metrics ? <TechnicalRows rows={Object.entries(metrics).slice(0, 10).map(([key, value]) => [key, typeof value === "number" ? value.toPrecision(5) : String(value)])} /> : <p className="empty-copy">Run validation to persist comparison metrics.</p>}
      </PanelSection>
      <Button variant="primary" onClick={() => void actions.run("validate", { surfaceDeviation: tolerance })} disabled={!vm.workerReady || !vm.serverWritable || !vm.project.state.cadgraph || Boolean(vm.activeJob)}><ShieldCheck size={16} />Run validation</Button>
    </InspectorFrame>
  );
}
