import type { ProjectDetail, ProjectWorkingDocument } from "../state/types";

/** Keep the UI resilient to older project documents without inventing domain results. */
export function normalizeProjectDetail(project: ProjectDetail): ProjectDetail {
  const raw = (project.state ?? {}) as Partial<ProjectWorkingDocument>;
  return {
    ...project,
    state: {
      schemaVersion: raw.schemaVersion ?? project.schemaVersion,
      projectId: raw.projectId ?? project.id,
      name: raw.name ?? project.name,
      units: raw.units ?? project.units,
      source: raw.source ?? null,
      diagnostics: raw.diagnostics ?? null,
      repair: raw.repair ?? null,
      analysis: raw.analysis ?? null,
      patches: raw.patches ?? [],
      cadgraph: raw.cadgraph ?? null,
      validation: raw.validation ?? null,
      metrics: raw.metrics ?? null,
      artifactSetId: raw.artifactSetId ?? null,
      artifacts: raw.artifacts ?? [],
      currentVersionId: raw.currentVersionId ?? project.basedOnVersionId,
      settings: raw.settings ?? {},
    },
  };
}
