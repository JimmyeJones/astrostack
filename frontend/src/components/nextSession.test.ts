import { describe, expect, it } from "vitest";
import {
  describeGap,
  describeWindow,
  formatGapHours,
  formatWindowDate,
  moonPhrase,
  subsToGo,
  windowsIntro,
} from "./nextSession";
import type { NextObservingWindow } from "../api/client";

function win(over: Partial<NextObservingWindow> = {}): NextObservingWindow {
  return {
    dark_start_utc: "2026-01-15T22:00:00+00:00",
    dark_end_utc: "2026-01-16T06:00:00+00:00",
    usable_start_utc: "2026-01-15T22:40:00+00:00",
    usable_end_utc: "2026-01-16T02:10:00+00:00",
    max_altitude_deg: 34.2,
    minutes_above_min_alt: 210,
    moon_illumination: 0.12,
    moon_up_fraction: 0.0,
    score: 62,
    ...over,
  };
}

describe("formatWindowDate", () => {
  it("formats a UTC ISO stamp as 'Wkd D Mon' without timezone drift", () => {
    // 2026-01-15 is a Thursday.
    expect(formatWindowDate("2026-01-15T22:00:00+00:00")).toBe("Thu 15 Jan");
  });
  it("returns empty for missing/unparseable input", () => {
    expect(formatWindowDate(null)).toBe("");
    expect(formatWindowDate("")).toBe("");
    expect(formatWindowDate("not-a-date")).toBe("");
  });
});

describe("subsToGo", () => {
  it("rounds up the gap divided by the typical sub length", () => {
    expect(subsToGo(600, 10)).toBe(60); // 600s / 10s = 60 subs
    expect(subsToGo(605, 10)).toBe(61); // rounds up a partial sub
  });
  it("is null when either figure is unknown or non-positive", () => {
    expect(subsToGo(0, 10)).toBeNull();
    expect(subsToGo(600, 0)).toBeNull();
    expect(subsToGo(600, null)).toBeNull();
    expect(subsToGo(600, undefined)).toBeNull();
  });
});

describe("formatGapHours", () => {
  it("uses rounded minutes under ~1.5 h", () => {
    expect(formatGapHours(20 * 60)).toBe("About 20 more clear minutes");
    expect(formatGapHours(44 * 60)).toBe("About 40 more clear minutes");
  });
  it("uses nearest-half hours above that", () => {
    expect(formatGapHours(2 * 3600)).toBe("About 2 more clear hours");
    expect(formatGapHours(2.25 * 3600)).toBe("About 2.5 more clear hours");
  });
});

describe("describeGap", () => {
  it("includes a subs estimate when the sub length is known", () => {
    const s = describeGap(2 * 3600, 10);
    expect(s).toContain("About 2 more clear hours");
    expect(s).toContain("720 more subs");
    expect(s).toContain("good picture");
  });
  it("omits the subs clause when the sub length is unknown", () => {
    const s = describeGap(2 * 3600, null);
    expect(s).toContain("About 2 more clear hours");
    expect(s).not.toContain("subs");
  });
});

describe("moonPhrase", () => {
  it("reassures when the Moon is out of the way while the target is up", () => {
    expect(moonPhrase(win({ moon_up_fraction: 0.0 }))).toBe("Moon out of the way");
  });
  it("calls a faint Moon thin", () => {
    expect(moonPhrase(win({ moon_illumination: 0.1, moon_up_fraction: 1.0 })))
      .toBe("thin Moon (10%)");
  });
  it("flags a bright Moon", () => {
    expect(moonPhrase(win({ moon_illumination: 0.8, moon_up_fraction: 1.0 })))
      .toBe("bright Moon (80%)");
  });
});

describe("describeWindow", () => {
  it("reads as a dated, plain-language shoot-between line", () => {
    const s = describeWindow(win());
    expect(s).toContain("Thu 15 Jan");
    expect(s).toContain("22:40 → 02:10 UTC");
    expect(s).toContain("climbs to 34°");
    expect(s).toContain("Moon out of the way");
  });
  it("falls back to the dark-window bounds when the usable ones are missing", () => {
    const s = describeWindow(win({ usable_start_utc: null, usable_end_utc: null }));
    expect(s).toContain("22:00 → 06:00 UTC");
  });
});

describe("windowsIntro", () => {
  it("is singular for one window and plural for more", () => {
    expect(windowsIntro(1)).toBe("Your next good window:");
    expect(windowsIntro(3)).toBe("Your next good windows:");
  });
});
