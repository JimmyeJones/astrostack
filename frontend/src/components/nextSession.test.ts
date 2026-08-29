import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import {
  describeGap,
  describeWindow,
  finishForecast,
  formatGapHours,
  formatWindowDate,
  moonPhrase,
  subsToGo,
  windowUtcTooltip,
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
  it("formats a UTC ISO stamp as 'Wkd D Mon' in the local timezone (TZ=UTC here)", () => {
    // The CI/test machine runs in UTC, so local == UTC: 2026-01-15 is a Thursday.
    expect(formatWindowDate("2026-01-15T22:00:00+00:00")).toBe("Thu 15 Jan");
  });
  it("returns empty for missing/unparseable input", () => {
    expect(formatWindowDate(null)).toBe("");
    expect(formatWindowDate("")).toBe("");
    expect(formatWindowDate("not-a-date")).toBe("");
  });
});

describe("west-of-UTC night labelling (regression)", () => {
  // Reproduces the reported bug: an owner in Seattle whose next dark window starts
  // at 06:17 UTC is actually going out on *Sunday* evening (23:17 local), but the
  // card used to format everything in UTC and call it "Mon 27 Jul" — disagreeing
  // with the .ics file and the adjacent "Point here tonight" card. With local
  // formatting the card must name the Sunday night, with UTC kept in the tooltip.
  beforeAll(() => { vi.stubEnv("TZ", "America/Los_Angeles"); });
  afterAll(() => { vi.unstubAllEnvs(); });

  const seattleWin = win({
    dark_start_utc: "2026-07-27T06:17:00+00:00",   // Sun 23:17 local
    dark_end_utc: "2026-07-27T11:30:00+00:00",
    usable_start_utc: "2026-07-27T06:40:00+00:00", // Sun 23:40 local
    usable_end_utc: "2026-07-27T10:10:00+00:00",   // Mon 03:10 local
  });

  it("labels the night by the local date, not the UTC date", () => {
    expect(formatWindowDate(seattleWin.dark_start_utc)).toBe("Sun 26 Jul");
    const line = describeWindow(seattleWin);
    expect(line).toContain("Sun 26 Jul");
    expect(line).not.toContain("Mon 27 Jul");   // the old, wrong label
    expect(line).toContain("23:40 → 03:10");     // local wall-clock, not "06:40 UTC"
    expect(line).not.toContain("UTC");           // the local line no longer says UTC
  });

  it("keeps the honest UTC anchor in the hover tooltip", () => {
    const tip = windowUtcTooltip(seattleWin);
    expect(tip).toBe("In UTC: Mon 27 Jul, 06:40 → 10:10");
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
  it("reads as a dated, plain-language shoot-between line (local clock; TZ=UTC here)", () => {
    const s = describeWindow(win());
    expect(s).toContain("Thu 15 Jan");
    expect(s).toContain("22:40 → 02:10");
    expect(s).toContain("climbs to 34°");
    expect(s).toContain("Moon out of the way");
  });
  it("falls back to the dark-window bounds when the usable ones are missing", () => {
    const s = describeWindow(win({ usable_start_utc: null, usable_end_utc: null }));
    expect(s).toContain("22:00 → 06:00");
  });
});

describe("windowsIntro", () => {
  it("is singular for one window and plural for more", () => {
    expect(windowsIntro(1)).toBe("Your next good window:");
    expect(windowsIntro(3)).toBe("Your next good windows:");
  });
});

describe("finishForecast", () => {
  const wins = [
    win({ dark_start_utc: "2026-01-15T22:00:00+00:00" }),  // Thu 15 Jan
    win({ dark_start_utc: "2026-01-18T22:00:00+00:00" }),  // Sun 18 Jan
    win({ dark_start_utc: "2026-01-24T22:00:00+00:00" }),  // Sat 24 Jan
  ];

  it("dates the finish off the n-th night the target is actually well-placed", () => {
    // Two nights of pace, but the second observable night is three days out —
    // the whole point: a bare "2 more nights" would have implied tomorrow.
    expect(finishForecast(2, wins)).toBe(
      "About 2 more good nights — if the next clear ones cooperate, you could "
      + "finish around Sun 18 Jan.");
  });

  it("words the last-night case as one night, not 'about 1'", () => {
    expect(finishForecast(1, wins)).toBe(
      "One more good night should finish this — if Thu 15 Jan stays clear, "
      + "that could be the one.");
  });

  it("stays silent when it can't see far enough ahead to name a date", () => {
    // The planner returns a capped list of windows; quoting the last one for a
    // 5-night goal would promise a finish date that's too early.
    expect(finishForecast(5, wins)).toBeNull();
    expect(finishForecast(4, wins)).toBeNull();
  });

  it("says nothing without a pace estimate, or once the goal is met", () => {
    expect(finishForecast(null, wins)).toBeNull();
    expect(finishForecast(undefined, wins)).toBeNull();
    expect(finishForecast(0, wins)).toBeNull();
    expect(finishForecast(-1, wins)).toBeNull();
    expect(finishForecast(Number.NaN, wins)).toBeNull();
  });

  it("says nothing when the planner found no windows at all", () => {
    expect(finishForecast(2, [])).toBeNull();
    expect(finishForecast(2, null)).toBeNull();
  });

  it("says nothing rather than a broken date when a window's stamp is junk", () => {
    expect(finishForecast(1, [win({ dark_start_utc: "not-a-date" })])).toBeNull();
  });

  it("rounds a fractional night estimate up to a whole night", () => {
    expect(finishForecast(1.2, wins)).toContain("Sun 18 Jan");
  });
});
