/**
 * Per-chunk size budgets for the web bundle.
 *
 * Vite's single 500 kB warning is not a useful gate here: the reconstruction
 * core's WebAssembly payload is inherently over a megabyte and will never meet
 * it, while a regression that doubles the initial-load JavaScript stays
 * comfortably under it. Budgets are therefore per chunk and cover both the uncompressed size
 * (what the browser must parse and compile) and the gzipped size (what it must
 * download), because the two move independently — the generated JSON-schema
 * validator, for instance, is 375 kB raw but only 37 kB gzipped.
 *
 * Any chunk above NEW_CHUNK_FLOOR_BYTES without a budget fails the check, so a
 * newly split-out chunk has to be given a deliberate limit rather than silently
 * escaping the gate.
 */
import { gzipSync } from "node:zlib";
import { readFile, readdir } from "node:fs/promises";
import { relative, resolve } from "node:path";

const root = resolve(process.cwd(), "apps/web/dist/assets");
const NEW_CHUNK_FLOOR_BYTES = 100 * 1024;

/** Matched against the chunk name with its content hash and extension stripped. */
const BUDGETS = [
  // Everything needed to render the landing page. The tightest budget in the
  // list: this is the only JavaScript on the critical path to first paint.
  { chunk: "index", extension: ".js", rawKb: 450, gzipKb: 140 },
  { chunk: "index", extension: ".css", rawKb: 70, gzipKb: 14 },
  // Fetched when a project is opened: the viewer, three.js, and the workspace UI.
  { chunk: "WorkspaceController", extension: ".js", rawKb: 1_350, gzipKb: 380 },
  { chunk: "WorkspaceController", extension: ".css", rawKb: 16, gzipKb: 4 },
  // Fetched only when a .mesh2param.json is saved or opened; almost all of it
  // is the generated CADGraph schema validator.
  { chunk: "projectFile", extension: ".js", rawKb: 430, gzipKb: 48 },
  // Runs off the main thread; only fetched for a browser-local conversion. All
  // geometry lives in the WebAssembly module below, so this chunk is the worker
  // protocol plus wasm-bindgen's glue and nothing else — a budget it can only
  // breach by growing a JavaScript geometry implementation again.
  { chunk: "geometry.worker", extension: ".js", rawKb: 60, gzipKb: 20 },
  // The reconstruction core itself. Deliberately exempt from any notion of a
  // "small" bundle and budgeted on its own terms; it is never on the
  // first-paint path. Measured at 1 789 kB raw / 636 kB gzip.
  { chunk: "mesh2param_wasm_bg", extension: ".wasm", rawKb: 1_900, gzipKb: 700 },
];

// Vite appends a fixed-width content hash, which may itself contain "-" or
// "_"; anchoring to exactly that width avoids eating hyphens that belong to the
// chunk name (geometry.worker, mesh2param_wasm_bg).
const CONTENT_HASH = /-[A-Za-z0-9_-]{8}$/;

function chunkName(file) {
  return file.replace(/\.(js|css|wasm)$/, "").replace(CONTENT_HASH, "");
}

const entries = (await readdir(root, { withFileTypes: true }))
  .filter((entry) => entry.isFile() && /\.(js|css|wasm)$/.test(entry.name));

const failures = [];
const rows = [];

for (const entry of entries) {
  const path = resolve(root, entry.name);
  const bytes = await readFile(path);
  const extension = entry.name.slice(entry.name.lastIndexOf("."));
  const name = chunkName(entry.name);
  const budget = BUDGETS.find((item) => item.chunk === name && item.extension === extension);
  const rawKb = bytes.length / 1024;
  const gzipKb = gzipSync(bytes).length / 1024;

  if (budget === undefined) {
    if (bytes.length > NEW_CHUNK_FLOOR_BYTES) {
      failures.push(
        `${relative(root, path)} is ${rawKb.toFixed(1)} kB and has no budget. `
        + "Add one to scripts/check_bundle_budgets.mjs, sized to what the chunk should cost.",
      );
    }
    continue;
  }

  rows.push({ name: `${name}${extension}`, rawKb, gzipKb, budget });
  if (rawKb > budget.rawKb) {
    failures.push(`${name}${extension} is ${rawKb.toFixed(1)} kB uncompressed, over its ${budget.rawKb} kB budget.`);
  }
  if (gzipKb > budget.gzipKb) {
    failures.push(`${name}${extension} is ${gzipKb.toFixed(1)} kB gzipped, over its ${budget.gzipKb} kB budget.`);
  }
}

// A budget whose chunk vanished usually means a rename or an accidental merge
// back into another chunk, which would silently retire the limit.
const missing = BUDGETS.filter((budget) =>
  budget.optional !== true && !rows.some((row) => row.name === `${budget.chunk}${budget.extension}`));
for (const budget of missing) {
  failures.push(
    `No ${budget.chunk}${budget.extension} chunk was emitted. `
    + "If the chunk was renamed or merged, update scripts/check_bundle_budgets.mjs to match.",
  );
}

for (const row of rows.sort((left, right) => right.rawKb - left.rawKb)) {
  process.stdout.write(
    `${row.name.padEnd(28)} ${row.rawKb.toFixed(1).padStart(9)} kB raw `
    + `(budget ${String(row.budget.rawKb).padStart(6)})  `
    + `${row.gzipKb.toFixed(1).padStart(8)} kB gzip (budget ${String(row.budget.gzipKb).padStart(5)})\n`,
  );
}

if (failures.length > 0) {
  for (const failure of failures) process.stderr.write(`${failure}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`\nBundle budgets passed for ${rows.length} chunks.\n`);
}
