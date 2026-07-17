import { describe, expect, it, vi } from "vitest";

import { backendAvailable } from "./client";

describe("backend execution selection", () => {
  it("selects a reachable ready backend", async () => {
    const ready = vi.fn().mockResolvedValue({
      data: { status: "ready", database: true, storage: true, supervisor: true },
      revision: null,
      requestId: "request-ready",
    });
    await expect(backendAvailable({ ready }, 100)).resolves.toBe(true);
    expect(ready).toHaveBeenCalledOnce();
  });

  it("falls back when the backend proxy is unavailable", async () => {
    const ready = vi.fn().mockRejectedValue(new Error("503 api_origin_not_configured"));
    await expect(backendAvailable({ ready }, 100)).resolves.toBe(false);
  });
});
