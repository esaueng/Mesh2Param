import { useState } from "react";
import { RotateCcw, Wrench } from "lucide-react";
import { Button, PanelSection } from "@mesh2param/ui";
import type { WorkspaceActions, WorkspaceViewModel } from "../workspace/types";
import { InspectorFrame } from "../workspace/InspectorFrame";
import { JobProgress, TechnicalRows } from "./shared";

const OPERATIONS = [
  { id: "removeDegenerateFaces", label: "Remove degenerate faces", defaultEnabled: true, supported: true },
  { id: "mergeDuplicateVertices", label: "Merge duplicate vertices", defaultEnabled: true, supported: true },
  { id: "removeDuplicateFaces", label: "Remove duplicate faces", defaultEnabled: true, supported: true },
  { id: "removeUnreferencedVertices", label: "Remove unreferenced vertices", defaultEnabled: true, supported: true },
  { id: "orientWinding", label: "Orient winding", defaultEnabled: true, supported: true },
  { id: "repairNormals", label: "Repair normals", defaultEnabled: true, supported: true },
  { id: "keepLargestComponent", label: "Keep largest component", defaultEnabled: false, supported: true },
  { id: "dropTinyComponents", label: "Drop tiny detached components", defaultEnabled: false, supported: true },
  { id: "fillSmallHoles", label: "Fill small holes", defaultEnabled: false, supported: true },
  { id: "lightSmoothing", label: "Light smoothing · unavailable", defaultEnabled: false, supported: false },
  { id: "constrainedDecimation", label: "Constrained decimation · unavailable", defaultEnabled: false, supported: false },
] as const;

export function RepairPanel({ vm, actions }: { vm: WorkspaceViewModel; actions: WorkspaceActions }) {
  const repair = vm.project.state.repair;
  const [enabled, setEnabled] = useState<Record<string, boolean>>(() => Object.fromEntries(
    OPERATIONS.map((operation) => [operation.id, operation.defaultEnabled]),
  ));
  const selected = OPERATIONS.filter((operation) => operation.supported && enabled[operation.id]).map((operation) => operation.id);
  return (
    <InspectorFrame
      step="repair"
      title="Repair"
      helper="Apply explicit reversible cleanup operations to an analysis copy."
      onStep={actions.setStep}
    >
      {vm.activeJob?.job.kind === "repair"
        ? <JobProgress state={vm.activeJob} onCancel={() => void actions.cancelJob()} />
        : null}
      <PanelSection title="Operations">
        <div className="check-list">
          {OPERATIONS.map((operation) => (
            <label key={operation.id} title={operation.supported ? undefined : "This operation is not implemented by the bounded repair engine."}>
              <input
                type="checkbox"
                checked={enabled[operation.id] ?? false}
                disabled={!operation.supported}
                onChange={(event) => setEnabled((current) => ({
                  ...current,
                  [operation.id]: event.currentTarget.checked,
                }))}
              />
              <span>{operation.label}</span>
            </label>
          ))}
        </div>
      </PanelSection>
      <PanelSection title="Before / after">
        {repair ? (
          <TechnicalRows rows={[
            ["Triangles", `${repair.sourceMetrics.triangleCount.toLocaleString()} → ${repair.resultMetrics.triangleCount.toLocaleString()}`],
            ["Vertices", `${repair.sourceMetrics.vertexCount.toLocaleString()} → ${repair.resultMetrics.vertexCount.toLocaleString()}`],
            ["Components", `${repair.sourceMetrics.connectedComponentCount} → ${repair.resultMetrics.connectedComponentCount}`],
            ["Watertight", `${repair.sourceMetrics.watertight ? "yes" : "no"} → ${repair.resultMetrics.watertight ? "yes" : "no"}`],
            ["Operations recorded", repair.operations.length],
          ]} />
        ) : <p className="empty-copy">No repair has been applied.</p>}
      </PanelSection>
      <div className="panel-actions">
        <Button
          variant="primary"
          onClick={() => void actions.run("repair", { operations: selected })}
          disabled={!vm.workerReady || !vm.serverWritable || !vm.project.state.source || selected.length === 0 || Boolean(vm.activeJob)}
        >
          <Wrench size={16} />Apply repair
        </Button>
        <Button disabled title="Restore is available from a saved project version after one is created.">
          <RotateCcw size={15} />Restore previous
        </Button>
      </div>
    </InspectorFrame>
  );
}
