import { useRef, useState } from "react";
import { Check, FileUp, ScanSearch } from "lucide-react";
import { Button, NumberField, PanelSection, SelectField } from "@mesh2param/ui";
import type { Units } from "@mesh2param/contracts";
import type { WorkspaceActions, WorkspaceViewModel } from "../workspace/types";
import { InspectorFrame } from "../workspace/InspectorFrame";
import { JobProgress, TechnicalRows } from "./shared";

export function ImportPanel({ vm, actions }: { vm: WorkspaceViewModel; actions: WorkspaceActions }) {
  const [units,setUnits]=useState<Units>(vm.project.units); const [scale,setScale]=useState(1); const input=useRef<HTMLInputElement>(null);
  const source=vm.project.state.source; const diagnostics=vm.project.state.diagnostics;
  return <InspectorFrame step="import" title="Import" helper="Preserve the original mesh, confirm units, then inspect its health." onStep={actions.setStep}>
    {vm.activeJob?.job.kind === "upload" || vm.activeJob?.job.kind === "analyze" || vm.activeJob?.job.kind === "sample_open" ? <JobProgress state={vm.activeJob} onCancel={() => void actions.cancelJob()}/> : null}
    <PanelSection title="Source mesh"><div className="upload-zone"><FileUp/><strong>{source?.originalFileName ?? "Drop STL, OBJ, or PLY"}</strong><span>{source ? `${formatBytes(source.byteSize)} · ${source.format.toUpperCase()}` : "Original bytes remain unchanged"}</span><Button onClick={()=>input.current?.click()} disabled={!vm.workerReady||!vm.serverWritable}>{source ? "Replace source" : "Choose mesh"}</Button><input ref={input} className="visually-hidden" aria-label="Choose source mesh" type="file" accept=".stl,.obj,.ply" onChange={e=>{const file=e.currentTarget.files?.[0];e.currentTarget.value="";if(file)void actions.upload(file,units,scale)}}/></div></PanelSection>
    <PanelSection title="Units and scale"><SelectField label="Source units" value={units} onChange={e=>setUnits(e.currentTarget.value as Units)}>{["mm","cm","m","in","ft"].map(unit=><option key={unit}>{unit}</option>)}</SelectField><NumberField label="Scale factor" value={scale} min="0.000001" step="0.1" onChange={e=>setScale(Number(e.currentTarget.value))}/><p className="panel-note">STL does not encode units. These values are recorded when you choose or replace the source; changing them alone does not modify the current source.</p></PanelSection>
    <PanelSection title="Mesh health">{diagnostics ? <TechnicalRows rows={[["Triangles",diagnostics.triangleCount.toLocaleString()],["Vertices",diagnostics.rawVertexCount.toLocaleString()],["Components",diagnostics.connectedComponentCount],["Dimensions",diagnostics.boundingDimensions.map(v=>v.toFixed(2)).join(" × ")+` ${vm.project.units}`],["Watertight",diagnostics.watertight],["Non-manifold edges",diagnostics.nonManifoldEdgeCount],["Open boundaries",diagnostics.openBoundaryCount],["Degenerate triangles",diagnostics.degenerateTriangleCount]]}/> : <p className="empty-copy">Run analysis to calculate mesh-health metrics.</p>}</PanelSection>
    <div className="panel-actions"><Button variant="primary" onClick={actions.confirmImport} disabled={!source || !source.unitsConfirmed || Boolean(vm.activeJob)}><Check size={16}/>Confirm import</Button><Button onClick={()=>void actions.run("analyze")} disabled={!vm.workerReady || !vm.serverWritable || !source || Boolean(vm.activeJob)}><ScanSearch size={16}/>Run analysis</Button></div>
  </InspectorFrame>;
}
function formatBytes(bytes:number){return bytes<1024*1024?`${(bytes/1024).toFixed(1)} KB`:`${(bytes/1024/1024).toFixed(1)} MB`}
