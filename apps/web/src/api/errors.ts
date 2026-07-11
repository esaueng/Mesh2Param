import type { ApiErrorDetails } from "../state/types";

interface ErrorEnvelopeBody {
  error?: {
    code?: unknown;
    summary?: unknown;
    detail?: unknown;
    phase?: unknown;
    projectId?: unknown;
    jobId?: unknown;
    recoverable?: unknown;
    recommendedAction?: unknown;
  };
  meta?: { requestId?: unknown };
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

export class ApiError extends Error implements ApiErrorDetails {
  readonly status: number;
  readonly code: string;
  readonly summary: string;
  readonly detail: string;
  readonly phase: string | null;
  readonly projectId: string | null;
  readonly jobId: string | null;
  readonly recoverable: boolean;
  readonly recommendedAction: string | null;
  readonly requestId: string | null;

  constructor(details: ApiErrorDetails, options?: ErrorOptions) {
    super(details.detail, options);
    this.name = "ApiError";
    this.status = details.status;
    this.code = details.code;
    this.summary = details.summary;
    this.detail = details.detail;
    this.phase = details.phase;
    this.projectId = details.projectId;
    this.jobId = details.jobId;
    this.recoverable = details.recoverable;
    this.recommendedAction = details.recommendedAction;
    this.requestId = details.requestId;
  }

  toJSON(): ApiErrorDetails {
    return {
      status: this.status,
      code: this.code,
      summary: this.summary,
      detail: this.detail,
      phase: this.phase,
      projectId: this.projectId,
      jobId: this.jobId,
      recoverable: this.recoverable,
      recommendedAction: this.recommendedAction,
      requestId: this.requestId,
    };
  }
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  let body: ErrorEnvelopeBody | null = null;
  try {
    body = (await response.json()) as ErrorEnvelopeBody;
  } catch {
    // The stable fallback below deliberately avoids exposing an HTML proxy page.
  }
  const error = body?.error;
  const summary = typeof error?.summary === "string" ? error.summary : `Request failed (${response.status})`;
  const detail = typeof error?.detail === "string" ? error.detail : summary;
  return new ApiError({
    status: response.status,
    code: typeof error?.code === "string" ? error.code : "http_error",
    summary,
    detail,
    phase: nullableString(error?.phase),
    projectId: nullableString(error?.projectId),
    jobId: nullableString(error?.jobId),
    recoverable: typeof error?.recoverable === "boolean" ? error.recoverable : response.status >= 500,
    recommendedAction: nullableString(error?.recommendedAction),
    requestId:
      nullableString(body?.meta?.requestId) ?? nullableString(response.headers.get("X-Request-ID")),
  });
}

export function normalizeApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof DOMException && error.name === "AbortError") {
    return new ApiError({
      status: 0,
      code: "request_aborted",
      summary: "Request cancelled",
      detail: "The request was cancelled before it completed.",
      phase: null,
      projectId: null,
      jobId: null,
      recoverable: true,
      recommendedAction: null,
      requestId: null,
    }, { cause: error });
  }
  const detail = error instanceof Error ? error.message : "The API could not be reached.";
  return new ApiError({
    status: 0,
    code: "network_error",
    summary: "API unavailable",
    detail,
    phase: null,
    projectId: null,
    jobId: null,
    recoverable: true,
    recommendedAction: "Continue locally and retry when the service is available.",
    requestId: null,
  }, { cause: error });
}

export function isRevisionConflict(error: unknown): error is ApiError {
  return error instanceof ApiError && (error.status === 409 || error.status === 412);
}
