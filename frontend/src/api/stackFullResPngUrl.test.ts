import { describe, expect, it } from "vitest";
import { api } from "./client";

describe("stackFullResPngUrl", () => {
  it("omits every optional param when none are given", () => {
    expect(api.stackFullResPngUrl("M_42", 9)).toBe(
      "/api/targets/M_42/stack-runs/9/full-res-png",
    );
  });

  it("keeps the bare north_up form", () => {
    expect(api.stackFullResPngUrl("M_42", 9, true)).toBe(
      "/api/targets/M_42/stack-runs/9/full-res-png?north_up=true",
    );
  });

  it("passes the Adjust sliders so the download is the picture on screen", () => {
    const url = api.stackFullResPngUrl("M_42", 9, false, 0.7, 0.5);
    expect(url).toContain("stretch=0.7");
    expect(url).toContain("black=0.5");
    expect(url).not.toContain("north_up");
  });

  it("sends neither slider unless both are given", () => {
    // A half-set pair would silently mean "the other one is the default",
    // which is not the look on screen — the server falls back to the run's
    // saved stretch instead.
    const url = api.stackFullResPngUrl("M_42", 9, false, 0.7, undefined);
    expect(url).not.toContain("stretch=");
    expect(url).not.toContain("black=");
  });
});
