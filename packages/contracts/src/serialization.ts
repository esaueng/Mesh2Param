import type { JsonValue } from "./types.generated.js";

export class SerializationError extends TypeError {
  constructor(message: string) {
    super(message);
    this.name = "SerializationError";
  }
}

function normalize(value: unknown, path = "$", seen = new Set<object>()): JsonValue {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new SerializationError(`${path} contains a non-finite number`);
    }
    return Object.is(value, -0) ? 0 : value;
  }
  if (Array.isArray(value)) {
    if (seen.has(value)) {
      throw new SerializationError(`${path} contains a cycle`);
    }
    seen.add(value);
    const result = value.map((item, index) => normalize(item, `${path}[${index}]`, seen));
    seen.delete(value);
    return result;
  }
  if (typeof value === "object") {
    const object = value as object;
    const prototype = Object.getPrototypeOf(object) as object | null;
    if (prototype !== Object.prototype && prototype !== null) {
      throw new SerializationError(`${path} must contain only plain JSON objects`);
    }
    if (seen.has(object)) {
      throw new SerializationError(`${path} contains a cycle`);
    }
    seen.add(object);
    const record = object as Record<string, unknown>;
    const result: Record<string, JsonValue> = {};
    for (const key of Object.keys(record).sort()) {
      const child = record[key];
      if (child === undefined) {
        throw new SerializationError(`${path}.${key} is undefined`);
      }
      result[key] = normalize(child, `${path}.${key}`, seen);
    }
    seen.delete(object);
    return result;
  }
  throw new SerializationError(`${path} contains unsupported ${typeof value}`);
}

/** Return recursively key-sorted JSON with a single trailing newline. */
export function canonicalJson(value: unknown): string {
  return `${JSON.stringify(normalize(value))}\n`;
}

export function canonicalJsonBytes(value: unknown): Uint8Array {
  return new TextEncoder().encode(canonicalJson(value));
}

/** Hash canonical JSON with Web Crypto (available in browsers and Node 20+). */
export async function contentSha256(value: unknown): Promise<string> {
  const encoded = canonicalJsonBytes(value);
  const bytes = new Uint8Array(encoded.byteLength);
  bytes.set(encoded);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes.buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
