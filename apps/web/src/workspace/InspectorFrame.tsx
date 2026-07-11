import { ChevronLeft, ChevronRight, CircleHelp } from "lucide-react";
import { Button, IconButton } from "@mesh2param/ui";
import type { ReactNode } from "react";
import type { WorkflowStep } from "../state/types";

const STEPS: WorkflowStep[] = ["import","repair","surfaces","features","refine","validate","export"];
export function InspectorFrame({ step, title, helper, children, onStep }: { step: WorkflowStep; title: string; helper: string; children: ReactNode; onStep(step: WorkflowStep): void }) {
  const index = STEPS.indexOf(step);
  return <section className="inspector-panel" data-inspector-panel={step} aria-labelledby={`inspector-${step}`}>
    <header className="inspector-header"><div><span>Workflow</span><h2 id={`inspector-${step}`}>{title}</h2></div><IconButton label={`Help for ${title} is included below`} disabled title="The guidance for this step is shown below."><CircleHelp size={17}/></IconButton><p>{helper}</p></header>
    <div className="inspector-body">{children}</div>
    <footer className="inspector-footer"><Button disabled={index<=0} onClick={() => onStep(STEPS[index-1]!)}><ChevronLeft size={15}/>Previous</Button><Button disabled={index>=STEPS.length-1} onClick={() => onStep(STEPS[index+1]!)}>Next<ChevronRight size={15}/></Button></footer>
  </section>;
}
