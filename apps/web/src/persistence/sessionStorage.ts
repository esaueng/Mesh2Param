type SessionStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function getSessionItem(
  key: string,
  storage: SessionStorage | null = browserSessionStorage(),
): string | null {
  if (storage === null) return null;
  try {
    return storage.getItem(key);
  } catch {
    // Storage access can be denied in private or policy-restricted contexts.
    return null;
  }
}

export function setSessionItem(
  key: string,
  value: string,
  storage: SessionStorage | null = browserSessionStorage(),
): void {
  if (storage === null) return;
  try {
    storage.setItem(key, value);
  } catch {
    // The current page remains usable even when its reload hint cannot persist.
  }
}

export function removeSessionItem(
  key: string,
  storage: SessionStorage | null = browserSessionStorage(),
): void {
  if (storage === null) return;
  try {
    storage.removeItem(key);
  } catch {
    // Best-effort cleanup: a denied storage area cannot retain a new value.
  }
}

function browserSessionStorage(): SessionStorage | null {
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null;
  }
}
