import { describe, expect, it } from "vitest";
import {
  bestMonthsVerdict,
  formatMonthRange,
  longestCircularRun,
  monthShades,
} from "./bestMonths";
import type { MonthObservability } from "../api/client";

/** Build 12 month rows from per-month usable minutes (and optional peak alt). */
function months(
  usable: number[],
  alt?: number[],
): MonthObservability[] {
  return usable.map((u, i) => ({
    month: i + 1,
    usable_dark_minutes: u,
    max_transit_alt_deg: alt ? alt[i] : u > 0 ? 45 : 5,
    dark_minutes: 400,
  }));
}

describe("longestCircularRun", () => {
  it("returns null when nothing is flagged", () => {
    expect(longestCircularRun([false, false, false])).toBeNull();
  });

  it("returns the whole range when all flagged", () => {
    expect(longestCircularRun(new Array(12).fill(true))).toEqual({
      start: 1,
      end: 12,
      length: 12,
    });
  });

  it("finds a run that wraps past December into January", () => {
    // Good in Nov, Dec, Jan, Feb → wraps the year boundary.
    const flags = [true, true, false, false, false, false, false, false, false, false, true, true];
    expect(longestCircularRun(flags)).toEqual({ start: 11, end: 2, length: 4 });
  });

  it("finds a mid-year run", () => {
    const flags = [false, false, false, false, true, true, true, false, false, false, false, false];
    expect(longestCircularRun(flags)).toEqual({ start: 5, end: 7, length: 3 });
  });
});

describe("formatMonthRange", () => {
  it("names a single month plainly", () => {
    expect(formatMonthRange(12, 12)).toBe("Dec");
  });
  it("joins a span with an en dash", () => {
    expect(formatMonthRange(11, 2)).toBe("Nov–Feb");
  });
});

describe("monthShades", () => {
  it("normalises to the best month and is all-zero when never above horizon", () => {
    const rows = months(new Array(12).fill(0), new Array(12).fill(-10));
    expect(monthShades(rows)).toEqual(new Array(12).fill(0));
  });

  it("peaks at 1.0 on the most-usable month", () => {
    const usable = [300, 200, 0, 0, 0, 0, 0, 0, 0, 0, 200, 300];
    const shades = monthShades(months(usable));
    expect(Math.max(...shades)).toBeCloseTo(1.0);
    expect(shades[0]).toBeCloseTo(1.0); // Jan is one of the 300-min peaks
    expect(shades[3]).toBe(0); // April unusable
  });
});

describe("bestMonthsVerdict", () => {
  it("returns null for a malformed (not 12-month) input", () => {
    expect(bestMonthsVerdict(months([1, 2, 3]))).toBeNull();
  });

  it("names a winter target's best wrap-around range and peak", () => {
    // Orion-like: usable Nov–Feb, peak in December.
    const usable = [290, 190, 40, 0, 0, 0, 0, 0, 0, 0, 290, 320];
    const v = bestMonthsVerdict(months(usable))!;
    expect(v.peakMonth).toBe(12);
    expect(v.text).toMatch(/Best around Nov–Mar/); // Nov,Dec,Jan,Feb,Mar usable
    expect(v.text).toMatch(/highest in Dec/);
    expect(v.text).toMatch(/Low or out of reach/);
  });

  it("names a mid-year target's summer range", () => {
    const usable = [0, 0, 0, 0, 120, 200, 220, 150, 0, 0, 0, 0];
    const v = bestMonthsVerdict(months(usable))!;
    expect(v.peakMonth).toBe(7);
    expect(v.text).toMatch(/Best around May–Aug/);
  });

  it("says up-all-year for a circumpolar target", () => {
    const v = bestMonthsVerdict(months(new Array(12).fill(300)))!;
    expect(v.text).toMatch(/Up all year/);
    expect(v.peakMonth).toBe(1); // earliest of the tied peaks
  });

  it("reports a never-rising target honestly and highlights nothing", () => {
    const rows = months(new Array(12).fill(0), new Array(12).fill(-20));
    const v = bestMonthsVerdict(rows)!;
    expect(v.peakMonth).toBeNull();
    expect(v.text).toMatch(/never climbs above the horizon/);
  });

  it("falls back to altitude with a caveat for a low-but-visible target", () => {
    // Never clears the floor (usable all 0) but does rise; peaks mid-year.
    const alt = [2, 5, 9, 14, 19, 21, 20, 16, 11, 6, 3, 1];
    const rows = months(new Array(12).fill(0), alt);
    const v = bestMonthsVerdict(rows)!;
    expect(v.peakMonth).toBe(6); // highest altitude month
    expect(v.text).toMatch(/stays low/);
    expect(v.text).toMatch(/Best around/);
  });
});
