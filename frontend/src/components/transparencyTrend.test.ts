import { describe, expect, it } from "vitest";
import {
  describeTransparencyTrend,
  formatClockUtc,
  sparklinePoints,
  transparencyVerdictBadge,
} from "./transparencyTrend";
import type { TransparencyTrend } from "../api/client";

function trend(over: Partial<TransparencyTrend> = {}): TransparencyTrend {
  return {
    verdict: "clear",
    points: [
      { t_utc: "2026-07-10T22:00:00+00:00", transparency: 1000 },
      { t_utc: "2026-07-10T22:30:00+00:00", transparency: 1010 },
    ],
    n_points: 2,
    median_transparency: 1005,
    early_transparency: 1000,
    late_transparency: 1010,
    start_utc: "2026-07-10T22:00:00+00:00",
    end_utc: "2026-07-10T23:30:00+00:00",
    degraded_after_utc: null,
    ...over,
  };
}

describe("formatClockUtc (re-exported)", () => {
  it("reads HH:MM straight off the ISO stamp (no timezone shift)", () => {
    expect(formatClockUtc("2026-07-10T01:30:00+00:00")).toBe("01:30");
    expect(formatClockUtc(null)).toBeNull();
  });
});

describe("transparencyVerdictBadge", () => {
  it("maps each verdict to a colour + label", () => {
    expect(transparencyVerdictBadge("degraded")).toEqual({ color: "yellow", label: "clouds rolled in" });
    expect(transparencyVerdictBadge("cleared")).toEqual({ color: "teal", label: "cleared up" });
    expect(transparencyVerdictBadge("clear")).toEqual({ color: "teal", label: "clear all night" });
  });
});

describe("describeTransparencyTrend", () => {
  it("reassures on a clear night", () => {
    const s = describeTransparencyTrend(trend({ verdict: "clear" }));
    expect(s).toContain("Clear all night");
    expect(s.toLowerCase()).toContain("held steady");
  });

  it("names when clouds rolled in, with reassurance the subs counted less", () => {
    const s = describeTransparencyTrend(trend({
      verdict: "degraded",
      degraded_after_utc: "2026-07-10T01:10:00+00:00",
    }));
    expect(s).toContain("hazier after 01:10 UTC");
    expect(s).toContain("counted less");
    expect(s.toLowerCase()).toContain("clearer night");
  });

  it("falls back to 'later in the night' when no degraded-after time is known", () => {
    const s = describeTransparencyTrend(trend({
      verdict: "degraded",
      degraded_after_utc: null,
    }));
    expect(s).toContain("later in the night");
  });

  it("celebrates a night that cleared up", () => {
    const s = describeTransparencyTrend(trend({ verdict: "cleared" }));
    expect(s).toContain("started hazy and cleared up");
    expect(s.toLowerCase()).toContain("heavy lifting");
  });
});

describe("sparklinePoints", () => {
  it("plots clearer (higher transparency) higher on the chart", () => {
    // Two points: a hazy one then a clear one → the clear point sits higher (smaller y).
    const pts = sparklinePoints([400, 1000], 100, 40, 2);
    const [p0, p1] = pts.split(" ").map((p) => p.split(",").map(Number));
    expect(p0[0]).toBeLessThan(p1[0]); // x increases left→right in capture order
    expect(p0[1]).toBeGreaterThan(p1[1]); // hazy (400) is lower down (larger y) than clear (1000)
  });

  it("centres a single point and never divides by zero on a flat series", () => {
    expect(sparklinePoints([500], 100, 40, 2)).toBe("50.0,2.0");
    const flat = sparklinePoints([500, 500, 500], 100, 40, 2);
    expect(flat).not.toContain("NaN");
  });

  it("returns an empty string with no points", () => {
    expect(sparklinePoints([], 100, 40)).toBe("");
  });
});
