import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { compile } from "json-schema-to-typescript";
import Ajv2020 from "ajv/dist/2020.js";
import standaloneCode from "ajv/dist/standalone/index.js";
import addFormats from "ajv-formats";

const packageRoot = fileURLToPath(new URL("..", import.meta.url));
const schemaPath = new URL("../schema/cadgraph.schema.json", import.meta.url);
const typesPath = new URL("../src/types.generated.ts", import.meta.url);
const validatorPath = new URL("../src/validator.generated.ts", import.meta.url);
const checkOnly = process.argv.includes("--check");

const schemaText = await readFile(schemaPath, "utf8");
const schema = JSON.parse(schemaText);
const hash = createHash("sha256").update(schemaText).digest("hex");
const banner = `/* eslint-disable */\n/**\n * GENERATED from schema/cadgraph.schema.json.\n * Schema SHA-256: ${hash}\n * Run \`pnpm generate\` in this package after changing the schema.\n */`;

const compiledTypes = await compile(schema, "CADGraph", {
  bannerComment: banner,
  cwd: packageRoot,
  declareExternallyReferenced: true,
  enableConstEnums: false,
  format: true,
  ignoreMinAndMaxItems: false,
  strictIndexSignatures: true,
  unreachableDefinitions: true,
  unknownAny: false,
});
// json-schema-to-typescript does not yet understand 2020-12's
// unevaluatedProperties. It emits permissive index signatures for the strict
// allOf definitions even though the schema rejects those keys. Remove only
// those synthetic `any` signatures; intentional JsonValue/string maps remain.
const types = compiledTypes.replaceAll("  [k: string]: any | undefined;\n", "");

const ajv = new Ajv2020({
  allErrors: true,
  strict: true,
  strictTypes: false,
  validateFormats: true,
  code: { esm: true, lines: true, source: true },
});
addFormats(ajv);
const compiledValidator = standaloneCode(ajv, ajv.compile(schema))
  .replace(/^"use strict";\n?/, "")
  .replace(
    /const (func\d+) = require\("ajv\/dist\/runtime\/ucs2length"\)\.default;/g,
    "const $1 = ucs2length;",
  )
  .replace(
    /const (func\d+) = require\("ajv\/dist\/runtime\/equal"\)\.default;/g,
    "const $1 = equal;",
  )
  .replace(
    /const (formats\d+) = require\("ajv-formats\/dist\/formats"\)\.fullFormats\["date-time"\];/g,
    'const $1 = fullFormats["date-time"];',
  );
if (compiledValidator.includes("require(")) {
  throw new Error("standalone CADGraph validator contains an unsupported CommonJS require");
}

const validator = `// @ts-nocheck -- generated Ajv standalone code is intentionally emitted as JavaScript.
/* eslint-disable */
/**
 * GENERATED from schema/cadgraph.schema.json.
 * Schema SHA-256: ${hash}
 */
import type { ErrorObject } from "ajv";
import equalModule from "ajv/dist/runtime/equal.js";
import ucs2lengthModule from "ajv/dist/runtime/ucs2length.js";
import { fullFormats } from "ajv-formats/dist/formats.js";

export const CADGRAPH_SCHEMA_VERSION = ${JSON.stringify(schema.properties.schemaVersion.const)} as const;
export const CADGRAPH_SCHEMA_SHA256 = ${JSON.stringify(hash)} as const;

const equal = typeof equalModule === "function" ? equalModule : equalModule.default;
const ucs2length = typeof ucs2lengthModule === "function" ? ucs2lengthModule : ucs2lengthModule.default;

${compiledValidator}

export interface SchemaValidationResult {
  valid: boolean;
  errors: ErrorObject[];
}

export function validateCADGraphSchema(value: unknown): SchemaValidationResult {
  const valid = validate(value);
  return { valid, errors: valid ? [] : [...(validate.errors ?? [])] };
}
`;

async function update(path, expected) {
  let actual = "";
  try {
    actual = await readFile(path, "utf8");
  } catch {
    // A missing generated file is a normal mismatch in check mode.
  }
  if (actual === expected) return;
  if (checkOnly) {
    throw new Error(`${fileURLToPath(path)} is stale; run pnpm generate`);
  }
  await writeFile(path, expected, "utf8");
}

await update(typesPath, types);
await update(validatorPath, validator);
