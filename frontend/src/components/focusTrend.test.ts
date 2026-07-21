import { describe, expect, it } from "vitest";
import {
  describeFocusTrend,
  focusVerdictBadge,
  formatClockUtc,
  sparklinePoints,
} from "./focusTrend";
import type { FocusTrend } from "../api/client";

function trend(over: Partial<FocusTrend> = {}): FocusTrend {
  return {
    verdict: "steady",
    points: [
      { t_utc: "2026-07-10T22:00:00+00:00", fwhm_px: 2.8 },
      { t_utc: "2026-07-10T22:30:00+00:00", fwhm_px: 2.9 },
    ],
    n_points: 2,
    median_fwhm_px: 2.85,
    early_fwhm_px: 2.8,
    late_fwhm_px: 2.9,
    start_utc: "2026-07-10T22:00:00+00:00",
    end_utc: "2026-07-10T23:30:00+00:00",
    soft_after_utc: null,
    ...over,
  };
}

describe("formatClockUtc", () => {
  it("reads HH:MM straight off the ISO stamp (no timezone shift)", () => {
    expect(formatClockUtc("2026-07-10T01:30:00+00:00")).toBe("01:30");
    expect(formatClockUtc("2026-07-10T23:05:00Z")).toBe("23:05");
  });
  it("returns null for a missing or unparseable stamp", () => {
    expect(formatClockUtc(null)).toBeNull();
    expect(formatClockUtc("nope")).toBeNull();
  });
});

describe("focusVerdictBadge", () => {
  it("maps each verdict to a colour + label", () => {
    expect(focusVerdictBadge("softened")).toEqual({ color: "yellow", label: "softened" });
    expect(focusVerdictBadge("improved")).toEqual({ color: "teal", label: "sharpened up" });
    expect(focusVerdictBadge("steady")).toEqual({ color: "teal", label: "steady" });
  });
});

describe("describeFocusTrend", () => {
  it("praises a steady night with the median sharpness", () => {
    const s = describeFocusTrend(trend({ verdict: "steady", median_fwhm_px: 2.83 }));
    expect(s).toContain("Sharp all night");
    expect(s).toContain("2.8 px");
  });

  it("names when a softening night drifted, with actionable advice", () => {
    const s = describeFocusTrend(trend({
      verdict: "softened",
      early_fwhm_px: 2.6,
      late_fwhm_px: 4.8,
      soft_after_utc: "2026-07-10T01:30:00+00:00",
    }));
    expect(s).toContain("softened after 01:30 UTC");
    expect(s).toContain("2.6 px → 4.8 px");
    expect(s.toLowerCase()).toContain("dew");
    expect(s).toContain("counted less");
  });

  it("falls back to 'later in the night' when no soft-after time is known", () => {
    const s = describeFocusTrend(trend({
      verdict: "softened",
      soft_after_utc: null,
    }));
    expect(s).toContain("later in the night");
  });

  it("celebrates an improving night", () => {
    const s = describeFocusTrend(trend({
      verdict: "improved",
      early_fwhm_px: 4.5,
      late_fwhm_px: 2.7,
    }));
    expect(s).toContain("sharpened up");
    expect(s).toContain("4.5 px → 2.7 px");
  });
});

describe("sparklinePoints", () => {
  it("plots sharper (lower FWHM) higher on the chart", () => {
    // Two points: a sharp one then a soft one → the sharp point sits higher (smaller y).
    const pts = sparklinePoints([2.0, 4.0], 100, 40, 2);
    const [p0, p1] = pts.split(" ").map((p) => p.split(",").map(Number));
    expect(p0[0]).toBeLessThan(p1[0]); // x increases left→right in capture order
    expect(p0[1]).toBeLessThan(p1[1]); // sharp (2.0) is higher up (smaller y) than soft (4.0)
  });

  it("centres a single point and never divides by zero on a flat series", () => {
    expect(sparklinePoints([3.0], 100, 40, 2)).toBe("50.0,2.0");
    // A perfectly flat series shouldn't NaN out.
    const flat = sparklinePoints([3.0, 3.0, 3.0], 100, 40, 2);
    expect(flat).not.toContain("NaN");
  });

  it("returns an empty string with no points", () => {
    expect(sparklinePoints([], 100, 40)).toBe("");
  });
});
