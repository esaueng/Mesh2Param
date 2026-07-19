import { readdir, stat } from "node:fs/promises";
import { relative, resolve } from "node:path";

const root = resolve(process.cwd(), "apps/web/dist");
const maximumBytes = 25 * 1024 * 1024;

async function files(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  return (await Promise.all(entries.map(async (entry) => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? files(path) : [path];
  }))).flat();
}

const assets = await files(root);
const measured = await Promise.all(assets.map(async (path) => ({ path, bytes: (await stat(path)).size })));
const oversized = measured.filter((asset) => asset.bytes > maximumBytes);
if (oversized.length > 0) {
  for (const asset of oversized) {
    process.stderr.write(`${relative(root, asset.path)} is ${asset.bytes} bytes; Cloudflare's per-asset limit is ${maximumBytes} bytes\n`);
  }
  process.exitCode = 1;
} else {
  const largest = measured.sort((left, right) => right.bytes - left.bytes)[0];
  process.stdout.write(`Cloudflare asset budget passed: ${assets.length} files; largest ${relative(root, largest.path)} is ${largest.bytes} bytes\n`);
}
