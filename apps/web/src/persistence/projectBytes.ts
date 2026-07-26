/**
 * Byte-level helpers and the shared error type for project persistence.
 *
 * These live apart from projectFile.ts on purpose. That module reaches
 * @mesh2param/contracts for CADGraph migration, which pulls in the generated
 * ajv schema validator — around 340 kB minified, and the single largest thing
 * in the app's initial bundle. Hashing a blob or decoding base64 has nothing
 * to do with schema validation, so the callers that only need these helpers
 * (the browser-local client, the repository's integrity checks) can import
 * them without dragging the validator onto the first-paint path.
 */

export const MAX_EMBEDDED_SOURCE_BYTES = 16 * 1024 * 1024;

export class ProjectFileError extends TypeError {
  readonly code: string;

  constructor(code: string, message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ProjectFileError";
    this.code = code;
  }
}

function decodedByteLength(base64: string): number {
  if (base64.length === 0 || base64.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(base64)) {
    throw new ProjectFileError("invalid_base64", "Embedded source is not valid base64.");
  }
  const padding = base64.endsWith("==") ? 2 : base64.endsWith("=") ? 1 : 0;
  return (base64.length / 4) * 3 - padding;
}

export function decodeBase64(base64: string, maximumBytes = MAX_EMBEDDED_SOURCE_BYTES): Uint8Array {
  const byteLength = decodedByteLength(base64);
  if (byteLength > maximumBytes) {
    throw new ProjectFileError("embedded_source_too_large", "Embedded source exceeds the configured size limit.");
  }
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

export function encodeBase64(bytes: Uint8Array): string {
  const chunks: string[] = [];
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 0x8000)));
  }
  return btoa(chunks.join(""));
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  if (globalThis.crypto?.subtle === undefined) {
    throw new ProjectFileError("crypto_unavailable", "SHA-256 verification is unavailable in this browser.");
  }
  const detached = Uint8Array.from(bytes).buffer;
  const digest = await globalThis.crypto.subtle.digest("SHA-256", detached);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

export async function readBlobBytes(blob: Blob): Promise<Uint8Array> {
  if (typeof blob.arrayBuffer === "function") return new Uint8Array(await blob.arrayBuffer());
  if (typeof FileReader === "undefined") {
    throw new ProjectFileError("blob_read_unavailable", "Blob content cannot be read in this environment.");
  }
  const buffer = await new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Blob read failed"));
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) resolve(reader.result);
      else reject(new Error("Blob reader did not return binary data"));
    };
    reader.readAsArrayBuffer(blob);
  });
  return new Uint8Array(buffer);
}
