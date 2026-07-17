import { Check, Grid3X3, ScanLine } from "lucide-react";
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

interface ViewSettingsProps {
  shading: ViewerShading;
  edges: boolean;
  disabled?: boolean;
  onPreferences(patch: Partial<ViewerPreferences>): void;
}

export function ViewSettings({
  shading,
  edges,
  disabled = false,
  onPreferences,
}: ViewSettingsProps) {
  return (
    <div className="view-settings" aria-label="View settings">
      <ViewSettingsGroup
        label="Surfaces"
        modes={SURFACE_MODES}
        selected={shading}
        disabled={disabled}
        onSelect={(next) => onPreferences({ shading: next })}
      />
      <ViewSettingsGroup
        label="Surface analysis"
        modes={ANALYSIS_MODES}
        selected={shading}
        disabled={disabled}
        onSelect={(next) => onPreferences({ shading: next })}
      />
      <div className="view-settings-group view-settings-options">
        <span className="view-settings-heading">Options</span>
        <button
          type="button"
          className="view-settings-toggle"
          role="switch"
          aria-checked={edges}
          disabled={disabled}
          onClick={() => onPreferences({ edges: !edges })}
        >
          <Grid3X3 size={16} />
          <span>Show edges</span>
          <span className="view-settings-switch" aria-hidden="true"><span /></span>
        </button>
      </div>
    </div>
  );
}

function ViewSettingsGroup({
  label,
  modes,
  selected,
  disabled,
  onSelect,
}: {
  label: string;
  modes: ReadonlyArray<{ id: ViewerShading; label: string; description: string }>;
  selected: ViewerShading;
  disabled: boolean;
  onSelect(mode: ViewerShading): void;
}) {
  return (
    <div className="view-settings-group" role="radiogroup" aria-label={label}>
      <span className="view-settings-heading">{label}</span>
      {modes.map((mode) => (
        <button
          key={mode.id}
          type="button"
          className="view-settings-option"
          role="radio"
          aria-checked={selected === mode.id}
          disabled={disabled}
          onClick={() => onSelect(mode.id)}
        >
          <span className="view-settings-check" aria-hidden="true">{selected === mode.id ? <Check size={15} /> : null}</span>
          <span className="view-settings-option-copy"><strong>{mode.label}</strong><small>{mode.description}</small></span>
          {mode.id === "zebra" ? <ScanLine className="view-settings-option-icon" size={16} aria-hidden="true" /> : null}
        </button>
      ))}
    </div>
  );
}
