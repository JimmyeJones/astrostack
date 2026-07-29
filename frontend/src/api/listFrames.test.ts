import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

// A synthetic frame page: the endpoint returns a plain array, so we only need
// objects with an `id` for these ordering/paging assertions.
function page(ids: number[]) {
  return ids.map((id) => ({ id }));
}

function stubPages(pages: unknown[]) {
  const calls: string[] = [];
  let i = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      const body = pages[Math.min(i, pages.length - 1)];
      i += 1;
      return {
        ok: true,
        status: 200,
        json: async () => body,
      } as Response;
    }),
  );
  return calls;
}

describe("listFrames paging", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns a single page unchanged when the target is small", async () => {
    const calls = stubPages([page([1, 2, 3])]);
    const frames = await api.listFrames("M_42");
    expect(frames.map((f) => f.id)).toEqual([1, 2, 3]);
    // A short first page proves the end was reached — only one request.
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain("offset=0");
    expect(calls[0]).toContain("limit=2000");
  });

  it("pages past the 2000 limit so the newest subs are never hidden", async () => {
    // 2,112 subs = one good S30 night; the old fixed limit=2000 dropped the
    // last 112. Two full-then-short pages must be concatenated whole.
    const first = page(Array.from({ length: 2000 }, (_, i) => i + 1));
    const second = page(Array.from({ length: 112 }, (_, i) => i + 2001));
    const calls = stubPages([first, second]);
    const frames = await api.listFrames("M_42");
    expect(frames).toHaveLength(2112);
    expect(frames[0].id).toBe(1);
    expect(frames[2111].id).toBe(2112);
    expect(calls).toHaveLength(2);
    expect(calls[1]).toContain("offset=2000");
  });

  it("stops after a full final page that happens to be an exact multiple", async () => {
    // Exactly 2000 frames: the first page is full, so we ask again; the empty
    // second page ends the loop without duplicating or looping forever.
    const first = page(Array.from({ length: 2000 }, (_, i) => i + 1));
    const calls = stubPages([first, []]);
    const frames = await api.listFrames("M_42");
    expect(frames).toHaveLength(2000);
    expect(calls).toHaveLength(2);
  });

  it("threads the sort and order through to every page request", async () => {
    const calls = stubPages([page([3, 2, 1])]);
    await api.listFrames("M_42", "fwhm_px", "desc");
    expect(calls[0]).toContain("sort=fwhm_px");
    expect(calls[0]).toContain("order=desc");
  });
});
