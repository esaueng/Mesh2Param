import { afterEach, describe, expect, it, vi } from "vitest";
import { apiAuthorizationHeaders, apiFetch, getApiToken, setApiToken } from "./auth";

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("API bearer token", () => {
  it("retains a normalized token only for the current tab", () => {
    setApiToken("  secret  ");
    expect(getApiToken()).toBe("secret");
    expect(apiAuthorizationHeaders()).toEqual({ Authorization: "Bearer secret" });
    setApiToken(null);
    expect(apiAuthorizationHeaders()).toEqual({});
  });

  it("adds authorization without dropping caller headers", async () => {
    setApiToken("secret");
    const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    await apiFetch("/api/projects", { headers: { Accept: "application/json" } });
    expect(fetcher).toHaveBeenCalledWith("/api/projects", expect.objectContaining({
      headers: { Authorization: "Bearer secret", Accept: "application/json" },
    }));
  });
});
