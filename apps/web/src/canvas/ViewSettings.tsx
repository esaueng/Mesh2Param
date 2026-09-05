import { Box, Compass, Grid2X2, Grid3X3, Layers, ScanLine, Sun } from "lucide-react";
import type { ReactNode } from "react";
import type { ViewerPreferences, ViewerShading } from "../state/types";

const SURFACE_MODES: ReadonlyArray<{ id: ViewerShading; label: string; description: string; icon: ReactNode }> = [
  { id: "shaded", label: "Shaded", description: "Lit solid surfaces", icon: <Box size={15} aria-hidden /> },
  { id: "wireframe", label: "Wireframe", description: "Mesh topology only", icon: <Grid3X3 size={15} aria-hidden /> },
  { id: "xray", label: "X-Ray", description: "Transparent surfaces", icon: <Layers size={15} aria-hidden /> },
];

const ANALYSIS_MODES: ReadonlyArray<{ id: ViewerShading; label: string; description: string; icon: ReactNode }> = [
  { id: "normals", label: "Surface normals", description: "Face orientation colors", icon: <Compass size={15} aria-hidden /> },
  { id: "zebra", label: "Zebra", description: "Continuity reflection bands", icon: <ScanLine size={15} aria-hidden /> },
];

interface ViewSettingsProps {
  shading: ViewerShading;
  edges: boolean;
  grid?: boolean;
  disabled?: boolean;
  onPreferences(patch: Partial<ViewerPreferences>): void;
  /** The grid is viewer chrome rather than a project preference, hence its own callback. */
  onGridChange?(grid: boolean): void;
}

/**
 * On-canvas display toolbar: a segmented control per shading family plus the
 * edge and grid switches. Accessible names live in aria-label so narrow
 * layouts can drop the visible text without changing what the controls are
 * called (the e2e suite addresses them by name).
 */
export function ViewSettings({
  shading,
  edges,
  grid = false,
  disabled = false,
  onPreferences,
  onGridChange,
}: ViewSettingsProps) {
  return (
    <div className="view-settings" role="toolbar" aria-label="View settings" aria-orientation="horizontal">
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
      <div className="view-settings-group view-settings-options" role="group" aria-label="Options">
        <button
          type="button"
          className="view-settings-toggle"
          role="switch"
          aria-checked={edges}
          aria-label="Show edges"
          title="Show edges"
          disabled={disabled}
          onClick={() => onPreferences({ edges: !edges })}
        >
          <Sun size={15} aria-hidden />
          <span className="view-settings-text">Edges</span>
        </button>
        <button
          type="button"
          className="view-settings-toggle"
          role="switch"
          aria-checked={grid}
          aria-label="Show grid"
          title="Show grid"
          disabled={disabled}
          onClick={() => onGridChange?.(!grid)}
        >
          <Grid2X2 size={15} aria-hidden />
          <span className="view-settings-text">Grid</span>
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
  modes: ReadonlyArray<{ id: ViewerShading; label: string; description: string; icon: ReactNode }>;
  selected: ViewerShading;
  disabled: boolean;
  onSelect(mode: ViewerShading): void;
}) {
  return (
    <div className="view-settings-group" role="radiogroup" aria-label={label}>
      {modes.map((mode) => (
        <button
          key={mode.id}
          type="button"
          className="view-settings-option"
          role="radio"
          aria-checked={selected === mode.id}
          aria-label={mode.label}
          title={`${mode.label} · ${mode.description}`}
          disabled={disabled}
          onClick={() => onSelect(mode.id)}
        >
          {mode.icon}
          <span className="view-settings-text">{mode.label}</span>
        </button>
      ))}
    </div>
  );
}
