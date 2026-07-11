import type {PropsWithChildren,ReactNode} from "react";
export function PanelSection({title,action,children,className=""}:PropsWithChildren<{title:string;action?:ReactNode;className?:string}>){return <section className={`ui-panel-section ${className}`.trim()}><div className="ui-panel-section__header"><h3>{title}</h3>{action}</div>{children}</section>}
