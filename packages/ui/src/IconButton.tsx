import type {ButtonHTMLAttributes,PropsWithChildren} from "react";
export function IconButton({label,className="",children,...props}:PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement>&{label:string}>){return <button className={`ui-icon-button ${className}`.trim()} aria-label={label} title={props.title??label} {...props}>{children}</button>}
