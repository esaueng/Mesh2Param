import { Activity, Keyboard, Save, Sparkles, Undo2, Redo2, Upload } from "lucide-react";
import { Button, IconButton } from "@mesh2param/ui";
import { useEffect, useState } from "react";
import { Mesh2ParamLogoMark } from "../start/Mesh2ParamLogoMark";
import type { WorkspaceActions, WorkspaceViewModel } from "./types";
import { automaticReconstructionCapability } from "./automaticReconstruction";

export function TopBar({vm,actions,onToggleShortcuts}:{vm:WorkspaceViewModel;actions:WorkspaceActions;onToggleShortcuts():void}){const [name,setName]=useState(vm.project.name);const automaticReconstruction=automaticReconstructionCapability(vm.project.state);useEffect(()=>setName(vm.project.name),[vm.project.name]);return <header className="topbar">
  <button className="topbar-brand" onClick={actions.openStart} aria-label="Back to start screen"><Mesh2ParamLogoMark/><strong>Mesh2Param</strong><span>Beta</span></button>
  <div className="topbar-divider"/><div className="breadcrumbs"><input aria-label="Project name" value={name} disabled={!vm.serverWritable} title={!vm.serverWritable?"Resolve queued local edits before renaming on the server.":undefined} onChange={e=>setName(e.currentTarget.value)} onBlur={()=>{if(name.trim()&&name!==vm.project.name)void actions.renameProject(name.trim())}}/><span>/</span><button disabled title="Version selection is available in the Export inspector.">{vm.project.state.currentVersionId??"Working copy"}</button></div>
  <div className="topbar-spacer"/><div className="topbar-history" role="group" aria-label="Undo and redo"><IconButton label="Undo last project edit" disabled={!actions.canUndo} onClick={actions.undo}><Undo2 size={17}/></IconButton><IconButton label="Redo project edit" disabled={!actions.canRedo} onClick={actions.redo}><Redo2 size={17}/></IconButton><IconButton label="Toggle single-key shortcuts" onClick={onToggleShortcuts}><Keyboard size={17}/></IconButton></div>
  <Button className="topbar-action secondary-action" onClick={()=>{actions.setStep("import");void actions.run("analyze")}} disabled={!vm.workerReady||!vm.serverWritable||!vm.project.state.source||Boolean(vm.activeJob)}><Activity size={16}/>Analyze</Button>
  <Button className="topbar-action secondary-action" variant="primary" title={automaticReconstruction.supported?undefined:automaticReconstruction.reason} onClick={()=>{actions.setStep("features");void actions.run("reconstruct")}} disabled={!automaticReconstruction.supported||!vm.workerReady||!vm.serverWritable||!vm.project.state.source||Boolean(vm.activeJob)}><Sparkles size={16}/>Auto reconstruct</Button>
  <Button className="topbar-action secondary-action" onClick={()=>actions.setStep("export")}><Upload size={16}/>Export STEP</Button>
  <Button className="topbar-action" variant="primary" onClick={()=>void actions.saveProject()}><Save size={16}/>Save project</Button>
 </header>}
