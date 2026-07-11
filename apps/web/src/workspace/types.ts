import type { ArtifactDescriptor, JobViewState, JsonObject, ProjectDetail, ProjectVersionSnapshot, SurfacePatch, WorkflowStep } from "../state/types";
import type { CADGraph, Units } from "@mesh2param/contracts";

export interface WorkspaceViewModel {
  project: ProjectDetail;
  activeStep: WorkflowStep;
  selectedPatchId: string | null;
  selectedFeatureId: string | null;
  activeJob: JobViewState | null;
  artifacts: ArtifactDescriptor[];
  versions: ProjectVersionSnapshot[];
  workerReady: boolean;
  syncLabel: string;
  serverWritable: boolean;
  error: string | null;
}

export interface WorkspaceActions {
  setStep(step: WorkflowStep): void;
  selectPatch(id: string | null): void;
  selectFeature(id: string | null): void;
  upload(file: File, units: Units, scale: number): Promise<void>;
  confirmImport(): void;
  run(operation: "repair" | "analyze" | "reconstruct" | "rebuild" | "validate" | "export", settings?: JsonObject): Promise<void>;
  cancelJob(): Promise<void>;
  updatePatch(patchId: string, patch: Partial<Pick<SurfacePatch,"name"|"hidden"|"locked">> & { classification?: SurfacePatch["type"] }): Promise<void>;
  mergePatches(patchIds: [string, string]): Promise<void>;
  updateCadgraph(graph: CADGraph, label: string): Promise<void>;
  undo(): void;
  redo(): void;
  canUndo: boolean;
  canRedo: boolean;
  renameProject(name: string): Promise<void>;
  saveProject(): Promise<void>;
  openStart(): void;
  createVersion(label: string): Promise<void>;
  restoreVersion(versionId: string): Promise<void>;
}
