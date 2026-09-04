import { describe, expect, it } from "vitest";
import type { NightActivity, YearRecap } from "./api/client";
import {
  defaultRecapYear, longestNightLines, recapYearOptions, sharpestNightLines,
} from "./yourYear";
import { formatIntegration } from "./format";

function night(over: Partial<NightActivity>): NightActivity {
  return {
    date: "2026-01-12", exposure_s: 3600, n_frames: 60, targets: ["M 31"],
    median_fwhm_px: null, n_measured: 0, ...over,
  };
}

function recap(over: Partial<YearRecap>): YearRecap {
  return {
    year: 2026, has_anything: true, headline: "", empty_message: "",
    stats: [], first_light_line: "", n_nights: 0, total_exposure_s: 0,
    n_frames: 0, n_targets: 0, target_names: [], first_lights: [],
    longest_night: null, sharpest_night: null, years_with_data: [], ...over,
  };
}

describe("defaultRecapYear", () => {
  it("opens on the most recent year that actually has nights", () => {
    // Clicking in on 3 January should land on the season you just finished, not
    // on a year three days old.
    expect(defaultRecapYear([2023, 2025, 2024], 2026)).toBe(2025);
  });

  it("falls back to the current year when nothing has been imaged", () => {
    expect(defaultRecapYear([], 2026)).toBe(2026);
    expect(defaultRecapYear(undefined, 2026)).toBe(2026);
  });

  it("prefers the current year when it already has nights", () => {
    expect(defaultRecapYear([2025, 2026], 2026)).toBe(2026);
  });
});

describe("recapYearOptions", () => {
  it("lists the years newest first", () => {
    expect(recapYearOptions(recap({ years_with_data: [2024, 2026, 2025] })))
      .toEqual([2026, 2025, 2024]);
  });

  it("always includes the year being viewed, even with nothing in it", () => {
    // Otherwise the picker would drop the current selection off its own list.
    expect(recapYearOptions(recap({ year: 2026, years_with_data: [2024] })))
      .toEqual([2026, 2024]);
  });

  it("is empty before the answer arrives", () => {
    expect(recapYearOptions(undefined)).toEqual([]);
  });
});

describe("longestNightLines", () => {
  it("words the year's longest night", () => {
    const lines = longestNightLines(
      night({ date: "2026-02-14", exposure_s: 7200, n_frames: 120 }),
      formatIntegration,
    );
    expect(lines?.value).toBe("2.0 h");
    expect(lines?.detail).toBe(
      "Your longest night of the year on M 31 — 120 subs kept.");
  });

  it("names two targets, and counts more than two", () => {
    expect(longestNightLines(
      night({ targets: ["M 31", "M 42"] }), formatIntegration)?.detail)
      .toContain("on M 31 and M 42");
    expect(longestNightLines(
      night({ targets: ["a", "b", "c"] }), formatIntegration)?.detail)
      .toContain("across 3 targets");
  });

  it("says nothing when the backend named no longest night", () => {
    // A one-night year has no "longest" — the server stays silent and so does
    // the card, rather than crowning the only night there was.
    expect(longestNightLines(null, formatIntegration)).toBeNull();
    expect(longestNightLines(undefined, formatIntegration)).toBeNull();
    expect(longestNightLines(night({ exposure_s: 0 }), formatIntegration)).toBeNull();
  });
});

describe("sharpestNightLines", () => {
  it("quotes star size in pixels, the unit the rest of the app uses", () => {
    const lines = sharpestNightLines(
      night({ date: "2026-03-03", median_fwhm_px: 2.44, n_measured: 40 }));
    expect(lines?.value).toBe("2.4 px stars");
    expect(lines?.detail).toBe(
      "Your steadiest sky of the year on M 31 — 40 subs measured.");
  });

  it("says nothing when too little was measured to name one", () => {
    expect(sharpestNightLines(null)).toBeNull();
    expect(sharpestNightLines(night({ median_fwhm_px: null }))).toBeNull();
    expect(sharpestNightLines(night({ median_fwhm_px: 0 }))).toBeNull();
  });
});
