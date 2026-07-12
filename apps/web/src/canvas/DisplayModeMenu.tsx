import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Eye, Grid3X3, ScanLine } from "lucide-react";
import type { ViewerPreferences, ViewerShading } from "../state/types";

const SURFACE_MODES: ReadonlyArray<{ id: ViewerShading; label: string; description: string }> = [
  { id: "shaded", label: "Shaded", description: "Lit solid surfaces" },
  { id: "wireframe", label: "Wireframe", description: "Mesh topology only" },
  { id: "xray", label: "X-Ray", description: "Transparent surfaces" },
];

const ANALYSIS_MODES: ReadonlyArray<{ id: ViewerShading; label: string; description: string }> = [
  { id: "normals", label: "Surface normals", description: "Face orientation colors" },
  { id: "zebra", label: "Zebra", description: "Continuity reflection bands" },
];

interface DisplayModeMenuProps {
  shading: ViewerShading;
  edges: boolean;
  theme: "dark" | "light";
  disabled?: boolean;
  onPreferences(patch: Partial<ViewerPreferences>): void;
}

export function DisplayModeMenu({
  shading,
  edges,
  theme,
  disabled = false,
  onPreferences,
}: DisplayModeMenuProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ right: 12, bottom: 72 });
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const placePopover = () => {
      const trigger = triggerRef.current;
      if (trigger === null) return;
      const rect = trigger.getBoundingClientRect();
      const mobile = window.innerWidth <= 640;
      setPosition(mobile
        ? { right: 12, bottom: 72 }
        : { right: Math.max(12, window.innerWidth - rect.right), bottom: window.innerHeight - rect.top + 12 });
    };
    placePopover();
    const closeOnPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !popoverRef.current?.contains(target)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointerdown", closeOnPointerDown);
    window.addEventListener("keydown", closeOnEscape);
    window.addEventListener("resize", placePopover);
    return () => {
      window.removeEventListener("pointerdown", closeOnPointerDown);
      window.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("resize", placePopover);
    };
  }, [open]);

  function selectShading(next: ViewerShading) {
    onPreferences({ shading: next });
    setOpen(false);
  }

  return (
    <div className="display-menu" ref={rootRef}>
      <button
        className={`dock-btn ${open ? "active" : ""}`}
        ref={triggerRef}
        type="button"
        aria-label="Display settings"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Display settings"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        <Eye size={17} />
      </button>

      {open ? createPortal(
        <div
          className={`display-popover ${theme === "light" ? "theme-light" : ""}`}
          ref={popoverRef}
          role="menu"
          aria-label="Display settings"
          style={position}
        >
          <DisplayGroup label="Surfaces" modes={SURFACE_MODES} selected={shading} onSelect={selectShading} />
          <DisplayGroup label="Surface analysis" modes={ANALYSIS_MODES} selected={shading} onSelect={selectShading} />
          <div className="display-group display-options">
            <span className="display-heading">Options</span>
            <button
              type="button"
              className="display-toggle"
              role="menuitemcheckbox"
              aria-checked={edges}
              onClick={() => onPreferences({ edges: !edges })}
            >
              <Grid3X3 size={16} />
              <span>Show edges</span>
              <span className="display-switch" aria-hidden="true"><span /></span>
            </button>
          </div>
        </div>,
        document.body,
      ) : null}
    </div>
  );
}

function DisplayGroup({
  label,
  modes,
  selected,
  onSelect,
}: {
  label: string;
  modes: ReadonlyArray<{ id: ViewerShading; label: string; description: string }>;
  selected: ViewerShading;
  onSelect(mode: ViewerShading): void;
}) {
  return (
    <div className="display-group" role="group" aria-label={label}>
      <span className="display-heading">{label}</span>
      {modes.map((mode) => (
        <button
          key={mode.id}
          type="button"
          className="display-option"
          role="menuitemradio"
          aria-checked={selected === mode.id}
          onClick={() => onSelect(mode.id)}
        >
          <span className="display-check" aria-hidden="true">{selected === mode.id ? <Check size={15} /> : null}</span>
          <span className="display-option-copy"><strong>{mode.label}</strong><small>{mode.description}</small></span>
          {mode.id === "zebra" ? <ScanLine className="display-option-icon" size={16} aria-hidden="true" /> : null}
        </button>
      ))}
    </div>
  );
}
