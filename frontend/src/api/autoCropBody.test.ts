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

  /** The three *classification* surfaces. Each asks "what is this picture?" about
   * the picture Auto is about to make, so each has to see the same per-run
   * override Auto does — the chip's endpoint has accepted one since v0.492.49 and
   * nothing sent it, which is why this went unnoticed. */
  it("sends the preference to the preset chip, which classifies the same picture",
    async () => {
      const fetchMock = mockFetch();
      await api.presetSuggestion("M_31", 5, false);
      const [path, init] = fetchMock.mock.calls[0];
      expect(path)
        .toBe("/api/targets/M_31/stack-runs/5/editor/preset-suggestion");
      expect(JSON.parse(init?.body as string)).toEqual({ auto_crop: false });
      await api.presetSuggestion("M_31", 5);
      expect(fetchMock.mock.calls[1][1]?.body).toBeUndefined();
    });

  it("sends the preference with a scoped feedback tap, so the cue is filed in the "
    + "bucket Auto reads", async () => {
    const fetchMock = mockFetch();
    await api.sendAutoFeedback("too_dark", { safe: "M_31", runId: 5 }, false);
    expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string))
      .toEqual({ cue: "too_dark", safe: "M_31", run_id: 5, auto_crop: false });
    // Omitted ⇒ the key is absent, not `null`: the server reads absent as "use the
    // saved setting", which is what every earlier build sent.
    await api.sendAutoFeedback("too_dark", { safe: "M_31", runId: 5 });
    expect(JSON.parse(fetchMock.mock.calls[1][1]?.body as string))
      .toEqual({ cue: "too_dark", safe: "M_31", run_id: 5 });
    // An unscoped tap has no run to classify, so it carries neither.
    await api.sendAutoFeedback("too_dark", undefined, false);
    expect(JSON.parse(fetchMock.mock.calls[2][1]?.body as string))
      .toEqual({ cue: "too_dark" });
  });

  it("carries the preference on the run-scoped profile GET as a query param",
    async () => {
      const fetchMock = mockFetch();
      await api.getRunAutoPreferences("M_31", 5, false);
      expect(fetchMock.mock.calls[0][0]).toBe(
        "/api/targets/M_31/stack-runs/5/editor/auto-preferences?auto_crop=false");
      await api.getRunAutoPreferences("M_31", 5, true);
      expect(fetchMock.mock.calls[1][0]).toBe(
        "/api/targets/M_31/stack-runs/5/editor/auto-preferences?auto_crop=true");
      // Omitted ⇒ the bare path, byte-for-byte what every earlier build asked for.
      await api.getRunAutoPreferences("M_31", 5);
      expect(fetchMock.mock.calls[2][0])
        .toBe("/api/targets/M_31/stack-runs/5/editor/auto-preferences");
    });
});
