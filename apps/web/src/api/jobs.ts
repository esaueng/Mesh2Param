import type { Job, JobConnectionState, JobEvent, JobEventType, JobStatus } from "../state/types";
import { apiClient } from "./client";
import { ApiError, normalizeApiError } from "./errors";

const EVENT_TYPES: readonly JobEventType[] = [
  "progress",
  "heartbeat",
  "log",
  "completed",
  "cancelled",
  "failed",
];
const TERMINAL_STATUSES = new Set(["completed", "cancelled", "failed"]);

interface EventSourceLike {
  readonly readyState: number;
  onopen: ((event: Event) => void) | null;
  onerror: ((event: Event) => void) | null;
  addEventListener(type: string, listener: EventListener): void;
  close(): void;
}

export interface JobEventHandlers {
  onConnection?(state: JobConnectionState): void;
  onEvent(event: JobEvent): void;
  onSnapshot?(job: Job): void;
  onInvalidEvent?(error: Error): void;
  onError?(error: ApiError): void;
}

export interface WatchJobOptions {
  client?: JobClient;
  eventSourceFactory?: (url: string) => EventSourceLike;
  reconnectDelayMs?: number;
}

interface JobClient {
  getJob(jobId: string): Promise<{ data: Job }>;
  subscribeJob?(jobId: string, listener: (event: JobEvent) => void): () => void;
}

interface StreamRegistration {
  generation: number;
  source: EventSourceLike | null;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  lastProgress: number;
  localUnsubscribe: (() => void) | null;
}

const streams = new Map<string, StreamRegistration>();
let streamGeneration = 0;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function nullableString(value: unknown, field: string): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") throw new TypeError(`job event ${field} must be a string or null`);
  return value;
}

export function parseJobEvent(value: string | unknown, expectedJobId?: string): JobEvent {
  const raw: unknown = typeof value === "string" ? JSON.parse(value) : value;
  if (!isRecord(raw)) throw new TypeError("job event must be an object");
  if (typeof raw.jobId !== "string" || (expectedJobId !== undefined && raw.jobId !== expectedJobId)) {
    throw new TypeError("job event has an unexpected jobId");
  }
  if (typeof raw.type !== "string" || !EVENT_TYPES.includes(raw.type as JobEventType)) {
    throw new TypeError("job event has an unsupported type");
  }
  if (typeof raw.phase !== "string" || typeof raw.timestamp !== "string") {
    throw new TypeError("job event phase and timestamp are required");
  }
  if (raw.progress !== null && raw.progress !== undefined) {
    if (typeof raw.progress !== "number" || !Number.isFinite(raw.progress) || raw.progress < 0 || raw.progress > 100) {
      throw new TypeError("job event progress must be in [0, 100]");
    }
  }
  const level = raw.level ?? "info";
  if (!new Set(["debug", "info", "warning", "error"]).has(String(level))) {
    throw new TypeError("job event level is invalid");
  }
  const status = raw.status;
  if (status !== undefined && !TERMINAL_STATUSES.has(String(status)) && status !== "queued" && status !== "running") {
    throw new TypeError("job event status is invalid");
  }
  const event: JobEvent = {
    jobId: raw.jobId,
    type: raw.type as JobEventType,
    phase: raw.phase,
    progress: typeof raw.progress === "number" ? raw.progress : null,
    level: level as JobEvent["level"],
    message: nullableString(raw.message, "message"),
    code: nullableString(raw.code, "code"),
    timestamp: raw.timestamp,
  };
  if (raw.detail !== undefined) event.detail = nullableString(raw.detail, "detail");
  if (typeof status === "string") event.status = status as JobStatus;
  if (isRecord(raw.result)) event.result = raw.result as NonNullable<JobEvent["result"]>;
  if (typeof raw.recoverable === "boolean") event.recoverable = raw.recoverable;
  if (raw.recommendedAction !== undefined) {
    event.recommendedAction = nullableString(raw.recommendedAction, "recommendedAction");
  }
  if (typeof raw.previousPhase === "string") event.previousPhase = raw.previousPhase;
  if (typeof raw.previousPhaseDurationMs === "number") {
    event.previousPhaseDurationMs = raw.previousPhaseDurationMs;
  }
  return event;
}

function defaultEventSourceFactory(url: string): EventSourceLike {
  return new EventSource(url);
}

function isTerminal(job: Job): boolean {
  return TERMINAL_STATUSES.has(job.status);
}

export function closeJobStream(jobId: string): void {
  const registration = streams.get(jobId);
  if (registration === undefined) return;
  registration.source?.close();
  registration.localUnsubscribe?.();
  if (registration.reconnectTimer !== null) clearTimeout(registration.reconnectTimer);
  streams.delete(jobId);
}

export function closeAllJobStreams(): void {
  for (const jobId of [...streams.keys()]) closeJobStream(jobId);
}

/** Subscribe to the authoritative SSE stream without placing EventSource in app state. */
export function watchJob(job: Job, handlers: JobEventHandlers, options: WatchJobOptions = {}): () => void {
  closeJobStream(job.id);
  const generation = ++streamGeneration;
  const registration: StreamRegistration = {
    generation,
    source: null,
    reconnectTimer: null,
    lastProgress: job.progress,
    localUnsubscribe: null,
  };
  streams.set(job.id, registration);
  const client = options.client ?? apiClient;
  const factory = options.eventSourceFactory ?? defaultEventSourceFactory;
  const reconnectDelay = options.reconnectDelayMs ?? 2_000;

  const current = (): boolean => streams.get(job.id)?.generation === generation;

  const acceptEvent = (event: JobEvent): void => {
    if (!current()) return;
    try {
      const parsed = parseJobEvent(event, job.id);
      if (parsed.progress !== null && parsed.progress < registration.lastProgress) {
        throw new TypeError("job event progress regressed");
      }
      if (parsed.progress !== null) registration.lastProgress = parsed.progress;
      handlers.onEvent(parsed);
      if (TERMINAL_STATUSES.has(parsed.type)) {
        registration.localUnsubscribe?.();
        streams.delete(job.id);
        handlers.onConnection?.("closed");
      }
    } catch (error) {
      handlers.onInvalidEvent?.(error instanceof Error ? error : new Error(String(error)));
    }
  };

  const connect = (): void => {
    if (!current()) return;
    handlers.onConnection?.("connecting");
    const source = factory(job.eventsUrl);
    registration.source = source;
    source.onopen = () => {
      if (current()) handlers.onConnection?.("open");
    };
    for (const eventType of EVENT_TYPES) {
      source.addEventListener(eventType, ((message: MessageEvent<string>) => {
        if (!current()) return;
        try {
          const event = parseJobEvent(message.data, job.id);
          if (event.progress !== null && event.progress < registration.lastProgress) {
            throw new TypeError("job event progress regressed");
          }
          if (event.progress !== null) registration.lastProgress = event.progress;
          handlers.onEvent(event);
          if (TERMINAL_STATUSES.has(event.type)) {
            source.close();
            streams.delete(job.id);
            handlers.onConnection?.("closed");
          }
        } catch (error) {
          handlers.onInvalidEvent?.(error instanceof Error ? error : new Error(String(error)));
        }
      }) as EventListener);
    }
    source.onerror = () => {
      if (!current()) return;
      if (source.readyState !== 2) {
        handlers.onConnection?.("reconnecting");
        return;
      }
      source.close();
      handlers.onConnection?.("reconnecting");
      void client.getJob(job.id).then(({ data: snapshot }) => {
        if (!current()) return;
        handlers.onSnapshot?.(snapshot);
        if (isTerminal(snapshot)) {
          streams.delete(job.id);
          handlers.onConnection?.("closed");
          return;
        }
        registration.lastProgress = snapshot.progress;
        registration.reconnectTimer = setTimeout(connect, reconnectDelay);
      }).catch((error: unknown) => {
        if (current()) handlers.onError?.(normalizeApiError(error));
      });
    };
  };

  if (isTerminal(job)) {
    streams.delete(job.id);
    handlers.onConnection?.("closed");
  } else if (client.subscribeJob !== undefined) {
    handlers.onConnection?.("open");
    registration.localUnsubscribe = client.subscribeJob(job.id, acceptEvent);
  } else {
    connect();
  }
  return () => closeJobStream(job.id);
}

export function hasActiveJobStream(jobId: string): boolean {
  return streams.has(jobId);
}
