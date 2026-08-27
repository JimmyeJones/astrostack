import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

describe("stackRenderUrl", () => {
  it("builds the stretch/black render URL and omits north_up by default", () => {
    const url = api.stackRenderUrl("M_31", 5, 0.4, 0.3);
    expect(url).toBe("/api/targets/M_31/stack-runs/5/render?stretch=0.4&black=0.3");
    expect(url).not.toContain("north_up");
  });

  it("appends north_up=true only when the North-up orientation is requested", () => {
    const url = api.stackRenderUrl("M_31", 5, 0.4, 0.3, true);
    expect(url).toContain("north_up=true");
    // Still carries the stretch/black so the two controls compose.
    expect(url).toContain("stretch=0.4");
    expect(url).toContain("black=0.3");
  });
});

describe("stackArtifactUrl", () => {
  it("builds the bare artifact URL and omits north_up by default", () => {
    expect(api.stackArtifactUrl("M_31", 5, "jpeg")).toBe(
      "/api/targets/M_31/stack-runs/5/jpeg");
    expect(api.stackArtifactUrl("M_31", 5, "preview")).toBe(
      "/api/targets/M_31/stack-runs/5/preview");
  });

  it("appends north_up=true only for the share-friendly JPEG", () => {
    expect(api.stackArtifactUrl("M_31", 5, "jpeg", true)).toBe(
      "/api/targets/M_31/stack-runs/5/jpeg?north_up=true");
    // The stored PNG/FITS/TIFF must stay WCS-aligned, so they never take north_up.
    expect(api.stackArtifactUrl("M_31", 5, "preview", true)).toBe(
      "/api/targets/M_31/stack-runs/5/preview");
    expect(api.stackArtifactUrl("M_31", 5, "fits", true)).toBe(
      "/api/targets/M_31/stack-runs/5/fits");
  });

  it("appends nameplate=true only for the JPEG, combining with north_up", () => {
    expect(api.stackArtifactUrl("M_31", 5, "jpeg", false, true)).toBe(
      "/api/targets/M_31/stack-runs/5/jpeg?nameplate=true");
    // Both toggles combine into one query string.
    expect(api.stackArtifactUrl("M_31", 5, "jpeg", true, true)).toBe(
      "/api/targets/M_31/stack-runs/5/jpeg?north_up=true&nameplate=true");
    // Non-JPEG artifacts never take the caption.
    expect(api.stackArtifactUrl("M_31", 5, "preview", false, true)).toBe(
      "/api/targets/M_31/stack-runs/5/preview");
  });

  it("appends keepsake=true only for the JPEG, combining with north_up", () => {
    expect(api.stackArtifactUrl("M_31", 5, "jpeg", false, false, true)).toBe(
      "/api/targets/M_31/stack-runs/5/jpeg?keepsake=true");
    expect(api.stackArtifactUrl("M_31", 5, "jpeg", true, false, true)).toBe(
      "/api/targets/M_31/stack-runs/5/jpeg?north_up=true&keepsake=true");
    // The framed card is a picture, not a science artifact.
    expect(api.stackArtifactUrl("M_31", 5, "fits", false, false, true)).toBe(
      "/api/targets/M_31/stack-runs/5/fits");
  });

  it("appends scale=true only for the JPEG, combining with north_up", () => {
    expect(api.stackArtifactUrl("M_31", 5, "jpeg", false, false, false, true)).toBe(
      "/api/targets/M_31/stack-runs/5/jpeg?scale=true");
    // The rose has to follow a North-up rotate, so the two combine.
    expect(api.stackArtifactUrl("M_31", 5, "jpeg", true, false, false, true)).toBe(
      "/api/targets/M_31/stack-runs/5/jpeg?north_up=true&scale=true");
    // …and the marks layer under the framed card rather than replacing it.
    expect(api.stackArtifactUrl("M_31", 5, "jpeg", false, false, true, true)).toBe(
      "/api/targets/M_31/stack-runs/5/jpeg?keepsake=true&scale=true");
    // Marks are for a picture, not for the science artifacts.
    expect(api.stackArtifactUrl("M_31", 5, "fits", false, false, false, true)).toBe(
      "/api/targets/M_31/stack-runs/5/fits");
  });

  it("leaves every existing caller byte-for-byte unchanged", () => {
    // keepsake and scale are the third and fourth optional flags, so no
    // positional call written before they existed can start asking for a framed
    // card or a marked picture by accident.
    expect(api.stackArtifactUrl("M_31", 5, "jpeg", true, true)).toBe(
      "/api/targets/M_31/stack-runs/5/jpeg?north_up=true&nameplate=true");
    expect(api.stackArtifactUrl("M_31", 5, "jpeg", false, false, true)).toBe(
      "/api/targets/M_31/stack-runs/5/jpeg?keepsake=true");
  });
});

describe("saveStackPreview", () => {
  afterEach(() => vi.restoreAllMocks());

  function mockFetch() {
    const fetchMock = vi.fn(
      async (_path: string, _init?: RequestInit) =>
        new Response(JSON.stringify({ ok: true }),
          { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("posts north_up:false by default so a normal save is WCS-aligned", async () => {
    const fetchMock = mockFetch();
    await api.saveStackPreview("M_31", 5, 0.4, 0.3);
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init?.body as string)).toEqual(
      { stretch: 0.4, black: 0.3, north_up: false });
  });

  it("posts north_up:true so saving under the North-up toggle persists the rotated image", async () => {
    const fetchMock = mockFetch();
    await api.saveStackPreview("M_31", 5, 0.4, 0.3, true);
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/targets/M_31/stack-runs/5/preview");
    expect(JSON.parse(init?.body as string)).toEqual(
      { stretch: 0.4, black: 0.3, north_up: true });
  });
});
