/* eslint-disable */
/**
 * GENERATED from schema/cadgraph.schema.json.
 * Schema SHA-256: 1e41231b9274c76cc6dfadb00859bbb5b226f5c28db1abf2359d78ba1c37ec54
 */
import Ajv2020, { type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import cadGraphSchema from "../schema/cadgraph.schema.json";
import type { CADGraph } from "./types.generated.js";

export const CADGRAPH_SCHEMA_VERSION = "1.0.0" as const;
export const CADGRAPH_SCHEMA_SHA256 = "1e41231b9274c76cc6dfadb00859bbb5b226f5c28db1abf2359d78ba1c37ec54" as const;

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
