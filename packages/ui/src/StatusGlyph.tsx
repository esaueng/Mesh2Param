import {AlertTriangle,Check,Circle,LoaderCircle,X} from "lucide-react";
export type SemanticState="idle"|"active"|"complete"|"warning"|"failed"|"disabled";
export function StatusGlyph({state,label,compact=false}:{state:SemanticState;label:string;compact?:boolean}){const Icon=state==="complete"?Check:state==="warning"?AlertTriangle:state==="failed"?X:state==="active"?LoaderCircle:Circle;return <span className={`ui-status ui-status--${state}`} title={label}><Icon size={compact?12:14} aria-hidden="true"/><span className={compact?"visually-hidden":""}>{label}</span></span>}
