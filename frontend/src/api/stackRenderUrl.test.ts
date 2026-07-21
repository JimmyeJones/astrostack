import { describe, expect, it } from "vitest";
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
});
