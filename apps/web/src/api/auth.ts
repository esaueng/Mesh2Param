import { getSessionItem, removeSessionItem, setSessionItem } from "../persistence/sessionStorage";

const API_TOKEN_KEY = "mesh2param-api-token:v1";

export function getApiToken(): string | null {
  const token = getSessionItem(API_TOKEN_KEY)?.trim() ?? "";
  return token || null;
}

export function setApiToken(token: string | null): void {
  const normalized = token?.trim() ?? "";
  if (normalized) setSessionItem(API_TOKEN_KEY, normalized);
  else removeSessionItem(API_TOKEN_KEY);
}

export function apiAuthorizationHeaders(): Record<string, string> {
  const token = getApiToken();
  return token === null ? {} : { Authorization: `Bearer ${token}` };
}

export function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  return fetch(input, {
    ...init,
    headers: { ...apiAuthorizationHeaders(), ...init.headers },
  });
}
