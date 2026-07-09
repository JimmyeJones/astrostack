import { describe, expect, it } from "vitest";
import {
  compassPoint, filterByTypeBucket, formatClock, formatMinutes, isoDate,
  minAltOptions, MAX_PLAN_LOOKAHEAD_DAYS, moonCueForTarget, moonPhaseLabel,
  moonWindowNote, objectTypeBucket, planDateBounds, planNightLabel, scoreColor,
  splitTargets, typeFilterOptions, usableWindowNote,
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

  it("weaves the waxing/waning state into the intermediate phases", () => {
    expect(moonPhaseLabel(0.2, true)).toBe("Waxing crescent (20%)");
    expect(moonPhaseLabel(0.2, false)).toBe("Waning crescent (20%)");
    expect(moonPhaseLabel(0.5, true)).toBe("First Quarter (50%)");
    expect(moonPhaseLabel(0.5, false)).toBe("Last Quarter (50%)");
    expect(moonPhaseLabel(0.8, true)).toBe("Waxing gibbous (80%)");
    expect(moonPhaseLabel(0.8, false)).toBe("Waning gibbous (80%)");
    // New / Full read the same either way, so they never take a prefix.
    expect(moonPhaseLabel(0, true)).toBe("New Moon (0%)");
    expect(moonPhaseLabel(1, false)).toBe("Full Moon (100%)");
    // An unknown state falls back to the plain, direction-agnostic labels.
    expect(moonPhaseLabel(0.8, null)).toBe("Gibbous (80%)");
  });
});

describe("moonWindowNote", () => {
  it("names a setting Moon with its concrete time", () => {
    const note = moonWindowNote({
      rise_utc: null, set_utc: "2026-01-26T01:03:00+00:00",
      up_all_night: false, down_all_night: false,
    });
    expect(note).toContain(`Sets ~${formatClock("2026-01-26T01:03:00+00:00")}`);
    expect(note).toContain("dark after");
    // The sentence is capitalised.
    expect(note?.[0]).toBe(note?.[0]?.toUpperCase());
  });

  it("names a rising Moon with its concrete time", () => {
    const note = moonWindowNote({
      rise_utc: "2026-01-12T02:34:00+00:00", set_utc: null,
      up_all_night: false, down_all_night: false,
    });
    expect(note).toContain(`~${formatClock("2026-01-12T02:34:00+00:00")}`);
    expect(note).toContain("dark before");
  });

  it("reports an all-night Moon plainly and hides the time", () => {
    expect(moonWindowNote({
      rise_utc: null, set_utc: null, up_all_night: true, down_all_night: false,
    })).toBe("Above the horizon all night");
    expect(moonWindowNote({
      rise_utc: null, set_utc: null, up_all_night: false, down_all_night: true,
    })).toBe("Below the horizon all night");
  });

  it("returns null when there's no useful cue", () => {
    expect(moonWindowNote(null)).toBeNull();
    expect(moonWindowNote(undefined)).toBeNull();
    expect(moonWindowNote({
      rise_utc: null, set_utc: null, up_all_night: false, down_all_night: false,
    })).toBeNull();
  });
});

describe("moonCueForTarget", () => {
  it("reassures when the Moon is down for the target's window", () => {
    expect(moonCueForTarget(0)).toBe("Moon down for its window");
    expect(moonCueForTarget(0.04)).toBe("Moon down for its window");
  });

  it("quantifies a partial overlap", () => {
    expect(moonCueForTarget(0.5)).toBe("Moon up 50% of its window");
    expect(moonCueForTarget(0.3)).toBe("Moon up 30% of its window");
  });

  it("omits the cue when the Moon is up for essentially the whole window", () => {
    // The separation column alone already tells the story there.
    expect(moonCueForTarget(1)).toBeNull();
    expect(moonCueForTarget(0.96)).toBeNull();
  });

  it("omits the cue when the fraction is unknown", () => {
    expect(moonCueForTarget(null)).toBeNull();
    expect(moonCueForTarget(undefined)).toBeNull();
    expect(moonCueForTarget(NaN)).toBeNull();
  });

  it("clamps out-of-range fractions", () => {
    expect(moonCueForTarget(-0.2)).toBe("Moon down for its window");
    expect(moonCueForTarget(1.5)).toBeNull();
  });
});

describe("usableWindowNote", () => {
  it("joins the two clock bounds with an en dash", () => {
    // Times render in the viewer's local zone / locale (12- or 24-hour), so
    // assert the two clock parts joined by an en dash rather than exact hours.
    const note = usableWindowNote("2026-01-15T21:00:00+00:00", "2026-01-16T04:30:00+00:00");
    expect(note).toMatch(/^\d{1,2}:\d{2}.*–.*\d{1,2}:\d{2}/);
    expect(note).toContain("–");
  });

  it("omits the line when either bound is missing", () => {
    expect(usableWindowNote(null, "2026-01-16T04:30:00+00:00")).toBeNull();
    expect(usableWindowNote("2026-01-15T21:00:00+00:00", null)).toBeNull();
    expect(usableWindowNote(null, null)).toBeNull();
    expect(usableWindowNote(undefined, undefined)).toBeNull();
  });

  it("omits the line when a bound is unparseable", () => {
    expect(usableWindowNote("not-a-date", "2026-01-16T04:30:00+00:00")).toBeNull();
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

describe("isoDate", () => {
  it("formats a Date as local YYYY-MM-DD, zero-padded", () => {
    expect(isoDate(new Date(2026, 6, 5))).toBe("2026-07-05"); // month is 0-based
    expect(isoDate(new Date(2026, 11, 31))).toBe("2026-12-31");
  });
});

describe("planDateBounds", () => {
  it("runs from today to +max-lookahead days", () => {
    const now = new Date(2026, 6, 15);
    const { min, max } = planDateBounds(now);
    expect(min).toBe("2026-07-15");
    const expected = new Date(2026, 6, 15);
    expected.setDate(expected.getDate() + MAX_PLAN_LOOKAHEAD_DAYS);
    expect(max).toBe(isoDate(expected));
    expect(new Date(max).getTime()).toBeGreaterThan(new Date(min).getTime());
  });
});

describe("planNightLabel", () => {
  const now = new Date(2026, 6, 15);
  it("is empty for tonight (no date, or today's date)", () => {
    expect(planNightLabel("", now)).toBe("");
    expect(planNightLabel(null, now)).toBe("");
    expect(planNightLabel("2026-07-15", now)).toBe("");
  });
  it("names a future night", () => {
    const label = planNightLabel("2026-08-01", now);
    expect(label).not.toBe("");
    expect(label).toMatch(/Aug/);
    expect(label).toMatch(/1/);
  });
  it("is empty for an unparseable date", () => {
    expect(planNightLabel("garbage", now)).toBe("");
  });
});

function typed(id: string, type: string): PlannedTarget {
  return { ...mk(id, false), type };
}

describe("objectTypeBucket", () => {
  it("coalesces the catalog's fine types into friendly buckets", () => {
    expect(objectTypeBucket("galaxy")).toBe("Galaxy");
    expect(objectTypeBucket("nebula")).toBe("Nebula");
    expect(objectTypeBucket("planetary nebula")).toBe("Nebula");
    expect(objectTypeBucket("supernova remnant")).toBe("Nebula");
    expect(objectTypeBucket("open cluster")).toBe("Cluster");
    expect(objectTypeBucket("globular cluster")).toBe("Cluster");
    expect(objectTypeBucket("star cloud")).toBe("Cluster");
    expect(objectTypeBucket("asterism")).toBe("Cluster");
    expect(objectTypeBucket("double star")).toBe("Other");
    expect(objectTypeBucket("")).toBe("Other");
    expect(objectTypeBucket(null)).toBe("Other");
  });
});

describe("typeFilterOptions", () => {
  it("lists All plus the present buckets in canonical order", () => {
    expect(typeFilterOptions([
      typed("a", "open cluster"), typed("b", "galaxy"),
      typed("c", "planetary nebula"), typed("d", "galaxy"),
    ])).toEqual(["All", "Galaxy", "Nebula", "Cluster"]);
  });
  it("collapses to just All when a single (or no) bucket is present", () => {
    expect(typeFilterOptions([typed("a", "galaxy"), typed("b", "galaxy")])).toEqual(["All"]);
    expect(typeFilterOptions([])).toEqual(["All"]);
  });
});

describe("filterByTypeBucket", () => {
  const targets = [
    typed("g", "galaxy"), typed("n", "nebula"), typed("c", "globular cluster"),
  ];
  it("filters to the chosen bucket", () => {
    expect(filterByTypeBucket(targets, "Nebula").map((t) => t.id)).toEqual(["n"]);
    expect(filterByTypeBucket(targets, "Cluster").map((t) => t.id)).toEqual(["c"]);
  });
  it("returns everything for All or a stale/unknown selection", () => {
    expect(filterByTypeBucket(targets, "All")).toHaveLength(3);
    expect(filterByTypeBucket(targets, "Nonexistent")).toHaveLength(3);
  });
});
