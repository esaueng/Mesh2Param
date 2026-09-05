/**
 * Cloudflare Workers Static Assets refuses any single file over 25 MiB, and it
 * refuses it at deploy time, so this runs before every `wrangler deploy`.
 *
 * The largest asset is the reconstruction core's WebAssembly module (~1.8 MB);
 * everything else is a bundled sample mesh. The check stays a hard per-file
 * ceiling rather than a budget: per-chunk budgets live in
 * `check_bundle_budgets.mjs`, and this one exists only to catch a file that
 * cannot be deployed at all.
 */
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
