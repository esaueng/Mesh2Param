const DOWNLOAD_SUFFIX_LENGTH = 5;
const DOWNLOAD_SUFFIX_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789";

export function randomDownloadSuffix(): string {
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(DOWNLOAD_SUFFIX_LENGTH));
  return suffixFromBytes(bytes);
}

export function suffixFromBytes(bytes: Uint8Array): string {
  if (bytes.length < DOWNLOAD_SUFFIX_LENGTH) {
    throw new RangeError(`download suffix requires at least ${DOWNLOAD_SUFFIX_LENGTH} random bytes`);
  }
  return Array.from(
    bytes.subarray(0, DOWNLOAD_SUFFIX_LENGTH),
    (byte) => DOWNLOAD_SUFFIX_ALPHABET[byte % DOWNLOAD_SUFFIX_ALPHABET.length],
  ).join("");
}

export function stepDownloadName(
  projectName: string,
  artifactName: string,
  suffix = randomDownloadSuffix(),
): string {
  if (!/^[a-z0-9]{5}$/.test(suffix)) {
    throw new TypeError("download suffix must be exactly five lowercase letters or digits");
  }
  const extension = /\.(step|stp)$/i.exec(artifactName)?.[0].toLowerCase() ?? ".step";
  const base = projectName
    .replace(/\.[^./\\]+$/, "")
    .replace(/[/\\?%*:|"<>]/g, "-")
    .trim();
  return `${base || "model"}-${suffix}${extension}`;
}
