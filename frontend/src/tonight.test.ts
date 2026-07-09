import { describe, expect, it } from "vitest";
import {
  compassPoint, formatMinutes, minAltOptions, moonPhaseLabel, scoreColor, splitTargets,
} from "./tonight";
import type { PlannedTarget } from "./api/client";

function mk(id: string, already: boolean, score = 50): PlannedTarget {
  return {
    id, name: id, ra_deg: 10, dec_deg: 20, type: "galaxy", con: "And",
    already_targeted: already, max_altitude_deg: 60, transit_utc: null,
    minutes_above_min_alt: 120, moon_separation_deg: 90, score,
    target_safe: already ? id : null, frames_accepted: already ? 10 : null,
    total_exposure_s: already ? 100 : null,
  };
}

describe("moonPhaseLabel", () => {
  it("buckets the illuminated fraction into friendly phases", () => {
    expect(moonPhaseLabel(0)).toContain("New Moon");
    expect(moonPhaseLabel(0.2)).toContain("Crescent");
    expect(moonPhaseLabel(0.5)).toContain("Quarter");
    expect(moonPhaseLabel(0.8)).toContain("Gibbous");
    expect(moonPhaseLabel(1)).toContain("Full Moon");
    expect(moonPhaseLabel(null)).toBe("—");
  });
});

describe("scoreColor", () => {
  it("maps score to a good/fair/poor colour", () => {
    expect(scoreColor(90)).toBe("teal");
    expect(scoreColor(50)).toBe("yellow");
    expect(scoreColor(10)).toBe("gray");
  });
});

describe("formatMinutes", () => {
  it("shows hours for long spans and minutes for short", () => {
    expect(formatMinutes(120)).toBe("2.0 h");
    expect(formatMinutes(45)).toBe("45 min");
    expect(formatMinutes(0)).toBe("—");
    expect(formatMinutes(-5)).toBe("—");
  });
});

describe("compassPoint", () => {
  it("labels the cardinal and intercardinal directions", () => {
    expect(compassPoint(0)).toBe("N");
    expect(compassPoint(90)).toBe("E");
    expect(compassPoint(180)).toBe("S");
    expect(compassPoint(270)).toBe("W");
    expect(compassPoint(45)).toBe("NE");
  });
  it("rounds to the nearest point and wraps past 360°", () => {
    expect(compassPoint(20)).toBe("N");   // nearer N than NE
    expect(compassPoint(30)).toBe("NE");  // nearer NE
    expect(compassPoint(360)).toBe("N");  // wraps
    expect(compassPoint(-90)).toBe("W");  // negative wraps
    expect(compassPoint(NaN)).toBe("");
  });
});

describe("minAltOptions", () => {
  const vals = (active: number | null | undefined) =>
    minAltOptions(active).map((o) => o.value);

  it("returns just the presets when the active floor is already one", () => {
    expect(vals(30)).toEqual(["10", "20", "30", "40", "50"]);
    expect(vals(10)).toEqual(["10", "20", "30", "40", "50"]);
    expect(vals(50)).toEqual(["10", "20", "30", "40", "50"]);
  });

  it("splices a non-preset active floor in, numerically sorted", () => {
    // 15° / 45° / 55° are all reachable from the step-5 Settings input.
    expect(vals(45)).toEqual(["10", "20", "30", "40", "45", "50"]);
    expect(vals(15)).toEqual(["10", "15", "20", "30", "40", "50"]);
    expect(vals(55)).toEqual(["10", "20", "30", "40", "50", "55"]);
    expect(vals(0)).toEqual(["0", "10", "20", "30", "40", "50"]);
  });

  it("labels the spliced option with its degree value", () => {
    const opt = minAltOptions(45).find((o) => o.value === "45");
    expect(opt?.label).toBe("45°");
  });

  it("rounds a fractional floor before matching / splicing", () => {
    expect(vals(30.4)).toEqual(["10", "20", "30", "40", "50"]);
    expect(vals(44.6)).toEqual(["10", "20", "30", "40", "45", "50"]);
  });

  it("falls back to the presets for a missing / non-finite floor", () => {
    expect(vals(null)).toEqual(["10", "20", "30", "40", "50"]);
    expect(vals(undefined)).toEqual(["10", "20", "30", "40", "50"]);
    expect(vals(NaN)).toEqual(["10", "20", "30", "40", "50"]);
  });
});

describe("splitTargets", () => {
  it("separates already-targeted from fresh, preserving order", () => {
    const { already, fresh } = splitTargets([
      mk("A", true), mk("B", false), mk("C", true), mk("D", false),
    ]);
    expect(already.map((t) => t.id)).toEqual(["A", "C"]);
    expect(fresh.map((t) => t.id)).toEqual(["B", "D"]);
  });
});
