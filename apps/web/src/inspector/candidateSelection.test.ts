import { describe, expect, it } from "vitest";
import type { CADGraph } from "@mesh2param/contracts";
import type { CandidateHistory, JsonObject } from "../state/types";
import {
  candidatesFromSettings,
  selectableCandidateGraph,
  selectedCandidateLabel,
} from "./candidateSelection";

const graph = {
  schemaVersion: "1.0.0",
  id: "candidate-graph",
  extensions: { "mesh2param.dev/reconstruction": { candidate: "measured" } },
} as unknown as CADGraph;

function candidate(overrides: Partial<CandidateHistory> = {}): CandidateHistory {
  return {
    label: "measured",
    score: 0.99,
    valid: true,
    rejectionReason: null,
    featureCount: 5,
    cadgraph: graph,
    kernel: {},
    comparison: null,
    ...overrides,
  };
}

describe("candidate history selection", () => {
  it("prefers the graph's authoritative reconstruction marker", () => {
    expect(selectedCandidateLabel(graph, { selectedCandidate: "nominal-preview" })).toBe("measured");
    expect(selectedCandidateLabel(null, { selectedCandidate: "nominal-preview" })).toBe("nominal-preview");
  });

  it("returns an isolated editable snapshot and rejects invalid candidates", () => {
    const selected = selectableCandidateGraph(candidate());
    expect(selected).toEqual(graph);
    expect(selected).not.toBe(graph);
    expect(() => selectableCandidateGraph(candidate({ valid: false }))).toThrow("rejected by the CAD kernel");
  });

  it("ignores malformed persisted entries instead of treating them as selectable", () => {
    const raw = [
      { ...candidate(), cadgraph: { schemaVersion: "1.0.0" } },
      { ...candidate(), label: 7 },
    ] as unknown as JsonObject["candidateHistories"];
    const parsed = candidatesFromSettings(raw);
    expect(parsed).toHaveLength(1);
    expect(parsed[0]?.cadgraph).toBeUndefined();
  });
});
