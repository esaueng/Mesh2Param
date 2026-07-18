import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface SwitchProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onChange"> {
  checked: boolean;
  onCheckedChange?(checked: boolean): void;
  label?: ReactNode;
}

export function Switch({ checked, onCheckedChange, label, className = "", onClick, ...props }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      className={`ui-switch ${className}`.trim()}
      onClick={(event) => {
        onClick?.(event);
        onCheckedChange?.(!checked);
      }}
      {...props}
    >
      <span className="ui-switch__track" aria-hidden="true">
        <span className="ui-switch__thumb" />
      </span>
      {label === undefined ? null : <span className="ui-switch__label">{label}</span>}
    </button>
  );
}
