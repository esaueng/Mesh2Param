/* eslint-disable */
/**
 * GENERATED from schema/cadgraph.schema.json.
 * Schema SHA-256: e56825a8ec3c4a3afdda9110560ce449d3e9fbf19dc2d5732b94b58696a65bec
 */
import Ajv2020, { type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import cadGraphSchema from "../schema/cadgraph.schema.json";
import type { CADGraph } from "./types.generated.js";

export const CADGRAPH_SCHEMA_VERSION = "1.0.0" as const;
export const CADGRAPH_SCHEMA_SHA256 = "e56825a8ec3c4a3afdda9110560ce449d3e9fbf19dc2d5732b94b58696a65bec" as const;

const ajv = new Ajv2020({
  allErrors: true,
  strict: true,
  // 2020-12 permits unevaluatedProperties alongside allOf without repeating
  // type: object. Ajv's optional strictTypes lint requires that repetition.
  strictTypes: false,
  validateFormats: true,
});
addFormats(ajv);
const validate = ajv.compile<CADGraph>(cadGraphSchema);

export interface SchemaValidationResult {
  valid: boolean;
  errors: ErrorObject[];
}

export function validateCADGraphSchema(value: unknown): SchemaValidationResult {
  const valid = validate(value);
  return { valid, errors: valid ? [] : [...(validate.errors ?? [])] };
}
