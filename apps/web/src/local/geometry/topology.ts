import { type OcctKernel, type ShapeHandle, type Vec3 } from "occt-wasm";

const HASH_UPPER_BOUND = 0x3fffffff;

function quantize(value: number, resolution: number): number {
  return Math.round(value / resolution);
}

function canonicalDirection(value: Vec3, resolution: number): [number, number, number] {
  const magnitude = Math.hypot(value.x, value.y, value.z);
  if (!Number.isFinite(magnitude) || magnitude <= Math.max(resolution, 1e-12)) return [0, 0, 0];
  const normalized = [value.x / magnitude, value.y / magnitude, value.z / magnitude] as [number, number, number];
  const first = normalized.find((component) => Math.abs(component) > Math.max(resolution, 1e-12));
  const sign = first !== undefined && first < 0 ? -1 : 1;
  return normalized.map((component) => quantize(component * sign, resolution)) as [number, number, number];
}

function subtract(left: Vec3, right: Vec3): Vec3 {
  return { x: left.x - right.x, y: left.y - right.y, z: left.z - right.z };
}

export interface BrowserEdgeDescriptor {
  kind: string;
  length: number;
  center: [number, number, number];
  bounds: [number, number, number, number, number, number];
  endpoints: Array<[number, number, number]>;
  direction: [number, number, number] | null;
}

export interface BrowserTopologyRecord {
  id: string;
  kind: "edge";
  producerFeatureId: string;
  status: "resolved";
  descriptor: BrowserEdgeDescriptor;
  hash: number;
}

interface RuntimeTopologyRecord extends BrowserTopologyRecord {
  shape: ShapeHandle;
}

function edgeDescriptor(kernel: OcctKernel, edge: ShapeHandle, resolution: number): BrowserEdgeDescriptor {
  const bounds = kernel.getBoundingBox(edge, false);
  const center = kernel.getLinearCenterOfMass(edge);
  const vertices = kernel.getSubShapes(edge, "vertex");
  const endpointValues = vertices.map((vertex) => kernel.vertexPosition(vertex));
  const endpoints = endpointValues.map((point) => [
    quantize(point.x, resolution),
    quantize(point.y, resolution),
    quantize(point.z, resolution),
  ] as [number, number, number]).sort((left, right) => (
    left[0] - right[0] || left[1] - right[1] || left[2] - right[2]
  ));
  const kind = kernel.curveType(edge);
  let direction: [number, number, number] | null = null;
  if (kind === "line" && endpointValues.length >= 2) {
    direction = canonicalDirection(subtract(endpointValues[1]!, endpointValues[0]!), resolution);
  }
  return {
    kind,
    length: quantize(kernel.curveLength(edge), resolution),
    center: [quantize(center.x, resolution), quantize(center.y, resolution), quantize(center.z, resolution)],
    bounds: [
      quantize(bounds.xmin, resolution), quantize(bounds.ymin, resolution), quantize(bounds.zmin, resolution),
      quantize(bounds.xmax, resolution), quantize(bounds.ymax, resolution), quantize(bounds.zmax, resolution),
    ],
    endpoints,
    direction,
  };
}

function descriptorKey(value: BrowserEdgeDescriptor): string {
  return JSON.stringify(value);
}

export class BrowserTopologyRegistry {
  private readonly records = new Map<string, RuntimeTopologyRecord>();

  constructor(
    private readonly kernel: OcctKernel,
    private readonly resolution: number,
  ) {}

  registerFeatureEdges(featureId: string, shape: ShapeHandle): string[] {
    const entries = this.kernel.getSubShapes(shape, "edge").map((edge) => ({
      edge,
      descriptor: edgeDescriptor(this.kernel, edge, this.resolution),
    }));
    entries.sort((left, right) => descriptorKey(left.descriptor).localeCompare(descriptorKey(right.descriptor)));
    return entries.map((entry, index) => {
      const id = `${featureId}.edge.${String(index + 1).padStart(3, "0")}`;
      this.records.set(id, {
        id,
        kind: "edge",
        producerFeatureId: featureId,
        status: "resolved",
        descriptor: entry.descriptor,
        hash: this.kernel.hashCode(entry.edge, HASH_UPPER_BOUND),
        shape: entry.edge,
      });
      return id;
    });
  }

  requireEdge(id: string, current: ShapeHandle): ShapeHandle {
    const record = this.records.get(id);
    if (record === undefined) throw new Error(`Semantic edge ${id} has not been produced`);
    const belongsToCurrent = this.kernel.getSubShapes(current, "edge").some((edge) => this.kernel.isSame(edge, record.shape));
    if (!belongsToCurrent) throw new Error(`Semantic edge ${id} no longer resolves on the current body`);
    return record.shape;
  }

  recordsForFeature(featureId: string): BrowserTopologyRecord[] {
    return [...this.records.values()]
      .filter((record) => record.producerFeatureId === featureId)
      .map(({ shape: _shape, ...record }) => record)
      .sort((left, right) => left.id.localeCompare(right.id));
  }
}

export function selectPrismaticRimEdges(
  records: readonly BrowserTopologyRecord[],
  axis: Vec3,
  angularEpsilon = 1e-6,
): string[] {
  const axisMagnitude = Math.hypot(axis.x, axis.y, axis.z);
  if (!Number.isFinite(axisMagnitude) || axisMagnitude <= 1e-12) throw new Error("Prismatic edge selection requires a finite axis");
  const normalized = [axis.x / axisMagnitude, axis.y / axisMagnitude, axis.z / axisMagnitude];
  const selected = records.filter((record) => {
    const direction = record.descriptor.direction;
    if (record.descriptor.kind !== "line" || direction === null) return true;
    const magnitude = Math.hypot(...direction);
    if (magnitude <= 0) return true;
    const alignment = Math.abs(
      direction[0] / magnitude * normalized[0]!
      + direction[1] / magnitude * normalized[1]!
      + direction[2] / magnitude * normalized[2]!,
    );
    return alignment < 1 - angularEpsilon;
  }).map((record) => record.id);
  if (selected.length < 4 || selected.length % 2 !== 0) {
    throw new Error("Resolved extrusion does not expose paired lower and upper profile-rim edges");
  }
  return selected;
}
