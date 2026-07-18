import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: ReactNode;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, className = "", ...props },
  ref,
) {
  return (
    <label className={`ui-checkbox ${className}`.trim()}>
      <input ref={ref} type="checkbox" {...props} />
      {label === undefined ? null : <span>{label}</span>}
    </label>
  );
});
