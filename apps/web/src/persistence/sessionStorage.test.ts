import { describe, expect, it, vi } from "vitest";
import { getSessionItem, removeSessionItem, setSessionItem } from "./sessionStorage";

describe("session storage access", () => {
  it("reads, writes, and removes values when storage is available", () => {
    const storage = {
      getItem: vi.fn(() => "project-1"),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };

    expect(getSessionItem("active", storage)).toBe("project-1");
    setSessionItem("active", "project-2", storage);
    removeSessionItem("active", storage);

    expect(storage.setItem).toHaveBeenCalledWith("active", "project-2");
    expect(storage.removeItem).toHaveBeenCalledWith("active");
  });

  it("fails closed when the browser denies storage access", () => {
    const denied = {
      getItem: vi.fn(() => { throw new DOMException("Denied", "SecurityError"); }),
      setItem: vi.fn(() => { throw new DOMException("Denied", "SecurityError"); }),
      removeItem: vi.fn(() => { throw new DOMException("Denied", "SecurityError"); }),
    };

    expect(getSessionItem("active", denied)).toBeNull();
    expect(() => setSessionItem("active", "project-1", denied)).not.toThrow();
    expect(() => removeSessionItem("active", denied)).not.toThrow();
  });
});
