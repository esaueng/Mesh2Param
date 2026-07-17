import { useState } from "react";
import { Eye, EyeOff, GitMerge, Lock, LockOpen, Scissors } from "lucide-react";
import type { PatchClassification, SurfacePatch } from "../state/types";

/**
 * Per-patch controls for the analyzed surface segmentation: lock, hide,
 * reclassify, and two-patch merge. Edits persist to the authoritative project
 * state and are honored by the curved reconstruction (a locked freeform patch
 * refuses splitting; reclassifications are refitted and fail closed when the
 * triangles do not satisfy the requested kind).
 */

export const PATCH_KINDS: readonly PatchClassification[] = [
  "plane",
  "cylinder",
  "cone",
  "sphere",
  "torus",
  "freeform",
  "unknown",
];

/** Mirror of the server's merge precondition so the button can explain itself. */
export function mergeBlockReason(a: SurfacePatch | undefined, b: SurfacePatch | undefined): string | null {
  if (a === undefined || b === undefined) return "Select exactly two patches to merge.";
  if (a.locked || b.locked) return "Unlock both patches before merging.";
  if (a.type !== b.type) return "Only patches with the same classification can merge.";
  if (JSON.stringify(a.fit ?? null) !== JSON.stringify(b.fit ?? null)) {
    return "Only patches with identical fitted parameters can merge; no refit is fabricated.";
  }
  return null;
}

export function patchSummary(patch: SurfacePatch): string {
  const parts: string[] = [];
  if (typeof patch.areaMm2 === "number") parts.push(`${patch.areaMm2.toFixed(1)} mm²`);
  if (patch.triangleCount !== null) parts.push(`${patch.triangleCount.toLocaleString()} tris`);
  const p95 = patch.residualsMm?.p95;
  if (typeof p95 === "number") parts.push(`p95 ${p95.toFixed(4)} mm`);
  return parts.join(" · ");
}

export interface PatchPanelProps {
  patches: readonly SurfacePatch[];
  selectedPatchId: string | null;
  disabled: boolean;
  onSelect(id: string | null): void;
  onUpdate(
    patchId: string,
    patch: { locked?: boolean; hidden?: boolean; classification?: PatchClassification },
  ): void;
  onMerge(patchIds: [string, string]): void;
}

export function PatchPanel({ patches, selectedPatchId, disabled, onSelect, onUpdate, onMerge }: PatchPanelProps) {
  const [mergeSelection, setMergeSelection] = useState<string[]>([]);
  const selected = patches.find((patch) => patch.id === selectedPatchId);
  const mergePair = mergeSelection
    .map((id) => patches.find((patch) => patch.id === id))
    .filter((patch): patch is SurfacePatch => patch !== undefined);
  const mergeReason =
    mergeSelection.length === 2 ? mergeBlockReason(mergePair[0], mergePair[1]) : "Select exactly two patches to merge.";

  const toggleMergeSelection = (id: string) => {
    setMergeSelection((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current.slice(-1), id],
    );
  };

  return (
    <section className="panel-group" aria-label="Surface patches">
      <h2 className="panel-label">Patches ({patches.length})</h2>
      <ul className="panel-patches" role="listbox" aria-label="Analyzed surface patches">
        {patches.map((patch) => (
          <li key={patch.id} className={patch.id === selectedPatchId ? "selected" : ""}>
            <input
              type="checkbox"
              aria-label={`Select ${patch.id} for merge`}
              checked={mergeSelection.includes(patch.id)}
              disabled={disabled}
              onChange={() => toggleMergeSelection(patch.id)}
            />
            <button
              className="panel-patch-row"
              role="option"
              aria-selected={patch.id === selectedPatchId}
              onClick={() => onSelect(patch.id === selectedPatchId ? null : patch.id)}
              title={patchSummary(patch)}
            >
              <span className={`patch-kind patch-kind-${patch.type}`}>{patch.type}</span>
              <span className="patch-meta">{patchSummary(patch)}</span>
            </button>
            <button
              className="panel-icon-btn"
              aria-label={patch.locked ? `Unlock ${patch.id}` : `Lock ${patch.id}`}
              aria-pressed={patch.locked}
              disabled={disabled}
              onClick={() => onUpdate(patch.id, { locked: !patch.locked })}
              title={patch.locked ? "Unlock patch" : "Lock patch (protects it from edits and splitting)"}
            >
              {patch.locked ? <Lock size={13} /> : <LockOpen size={13} />}
            </button>
            <button
              className="panel-icon-btn"
              aria-label={patch.hidden === true ? `Show ${patch.id}` : `Hide ${patch.id}`}
              aria-pressed={patch.hidden === true}
              disabled={disabled}
              onClick={() => onUpdate(patch.id, { hidden: patch.hidden !== true })}
              title={patch.hidden === true ? "Show patch" : "Hide patch"}
            >
              {patch.hidden === true ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
          </li>
        ))}
      </ul>

      {selected !== undefined ? (
        <div className="panel-patch-detail">
          <label className="panel-field">
            <span>Classification</span>
            <select
              aria-label="Reclassify selected patch"
              value={selected.type}
              disabled={disabled || selected.locked}
              onChange={(event) =>
                onUpdate(selected.id, { classification: event.currentTarget.value as PatchClassification })
              }
            >
              {PATCH_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>
          {selected.locked ? <p className="panel-hint info">Locked: unlock to reclassify.</p> : null}
          {selected.userOverriddenClassification === true ? (
            <p className="panel-hint info">User override: the next conversion refits and fails closed if the triangles do not satisfy this kind.</p>
          ) : null}
        </div>
      ) : null}

      <div className="panel-patch-actions">
        <button
          className="panel-btn"
          disabled={disabled || mergeReason !== null}
          title={mergeReason ?? "Merge the two selected patches"}
          onClick={() => {
            if (mergeSelection.length === 2 && mergeReason === null) {
              onMerge([mergeSelection[0] as string, mergeSelection[1] as string]);
              setMergeSelection([]);
            }
          }}
        >
          <GitMerge size={14} />
          Merge
        </button>
        <button
          className="panel-btn"
          disabled
          title="Patch splitting by triangle selection is not implemented; the server rejects it explicitly."
        >
          <Scissors size={14} />
          Split
        </button>
      </div>
    </section>
  );
}
