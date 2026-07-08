import { describe, expect, it } from "vitest";
import {
  formatMinutes, moonPhaseLabel, scoreColor, splitTargets,
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

describe("splitTargets", () => {
  it("separates already-targeted from fresh, preserving order", () => {
    const { already, fresh } = splitTargets([
      mk("A", true), mk("B", false), mk("C", true), mk("D", false),
    ]);
    expect(already.map((t) => t.id)).toEqual(["A", "C"]);
    expect(fresh.map((t) => t.id)).toEqual(["B", "D"]);
  });
});
