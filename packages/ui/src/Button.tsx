import type { ButtonHTMLAttributes, PropsWithChildren } from "react";
export type ButtonVariant="primary"|"secondary"|"ghost"|"danger";
export function Button({variant="secondary",className="",children,...props}:PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement>&{variant?:ButtonVariant}>){return <button className={`ui-button ui-button--${variant} ${className}`.trim()} {...props}>{children}</button>}
