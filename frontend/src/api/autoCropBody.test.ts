import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

/** The per-run "should Auto trim the ragged border?" override the editor sends.
 * Omitting it must post *no body at all*, so the backend falls back to the saved
 * `auto_crop_border` setting exactly as it does for an older frontend. */
describe("auto endpoints — auto_crop body", () => {
  afterEach(() => vi.restoreAllMocks());

  function mockFetch() {
    const fetchMock = vi.fn(
      async (_path: string, _init?: RequestInit) =>
        new Response(JSON.stringify({ ops: [] }),
          { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("sends no body when no preference is given", async () => {
    const fetchMock = mockFetch();
    await api.autoProcess("M_31", 5);
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/targets/M_31/stack-runs/5/editor/auto");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeUndefined();
  });

  it("sends auto_crop:false when the user turned the crop off", async () => {
    const fetchMock = mockFetch();
    await api.autoProcess("M_31", 5, false);
    expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string))
      .toEqual({ auto_crop: false });
  });

  it("sends auto_crop:true explicitly, so it can override a setting that is off",
    async () => {
      const fetchMock = mockFetch();
      await api.autoProcess("M_31", 5, true);
      expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string))
        .toEqual({ auto_crop: true });
    });

  it("threads the same preference through the auto-analysis sibling, so the "
    + "reported cues match the recipe", async () => {
    const fetchMock = mockFetch();
    await api.autoAnalysis("M_31", 5, false);
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/targets/M_31/stack-runs/5/editor/auto-analysis");
    expect(JSON.parse(init?.body as string)).toEqual({ auto_crop: false });
    await api.autoAnalysis("M_31", 5);
    expect(fetchMock.mock.calls[1][1]?.body).toBeUndefined();
  });
});
