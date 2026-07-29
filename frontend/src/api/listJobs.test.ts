import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

function stubFetch() {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      return { ok: true, status: 200, json: async () => [] } as Response;
    }),
  );
  return calls;
}

describe("listJobs", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("asks for the whole retained history, not the endpoint's default 100", async () => {
    // Regression: the Jobs page was pinned to the backend's default 100 rows, so
    // the "Job history to keep" setting (default 200) had no visible effect. We
    // now request up to the backend's hard 2000 cap.
    const calls = stubFetch();
    await api.listJobs();
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain("/api/jobs?limit=2000");
  });

  it("honours an explicit limit when one is passed", async () => {
    const calls = stubFetch();
    await api.listJobs(500);
    expect(calls[0]).toContain("/api/jobs?limit=500");
  });
});
