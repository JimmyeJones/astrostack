import { describe, expect, it } from "vitest";
import {
  CLOSING_WHY, closingHeadline, closingTargetLine, lastNightLabel, weeksLeftPhrase,
} from "./closingSeason";
import type { ClosingTarget, SeasonClosing } from "./api/client";

function row(over: Partial<ClosingTarget> = {}): ClosingTarget {
  return {
    safe: "m_42", name: "M 42", minutes_now: 180, weeks_left: 3,
    last_night: "2026-03-03", total_exposure_s: 3600, noise_gain: 0.29,
    ...over,
  };
}

function plan(targets: ClosingTarget[]): SeasonClosing {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    generated_utc: "2026-01-20T21:00:00+00:00",
    min_altitude_deg: 30, horizon_weeks: 8, targets,
  };
}

describe("weeksLeftPhrase", () => {
  it("counts in weeks, and says so when there is no next week", () => {
    expect(weeksLeftPhrase(0)).toBe("this is its last week");
    expect(weeksLeftPhrase(1)).toBe("about a week left");
    expect(weeksLeftPhrase(5)).toBe("about 5 weeks left");
  });

  it("never invents a negative or fractional countdown", () => {
    // The scan samples whole weeks, so anything else is a bug upstream — this
    // must degrade to a sentence, never to "about -1 weeks left".
    expect(weeksLeftPhrase(-4)).toBe("this is its last week");
    expect(weeksLeftPhrase(2.4)).toBe("about 2 weeks left");
  });
});

describe("lastNightLabel", () => {
  it("names the evening's own date, and hands back anything it can't parse", () => {
    // Parsed at local noon: a timezone offset must not roll the evening onto
    // the neighbouring day.
    expect(lastNightLabel("2026-03-03")).toContain("3");
    expect(lastNightLabel("not-a-date")).toBe("not-a-date");
  });
});

describe("closingTargetLine", () => {
  it("says how long is left and what you already have on it", () => {
    const line = closingTargetLine(row());
    expect(line).toContain("about 3 weeks left");
    expect(line).toContain("you have 1.0 h on it");
    expect(line).toContain("last good night around");
  });

  it("is honest about a target with nothing kept yet", () => {
    // "you have — on it" would be worse than useless; a target you have not
    // actually kept anything of is the one most worth a clear night.
    expect(closingTargetLine(row({ total_exposure_s: 0 })))
      .toContain("you haven't kept any of it yet");
  });
});

describe("closingHeadline", () => {
  it("says nothing at all when nothing is leaving", () => {
    // The ordinary answer for most of the year, and what keeps the card from
    // being one more always-on banner.
    expect(closingHeadline(plan([]))).toBeNull();
    expect(closingHeadline(null)).toBeNull();
    expect(closingHeadline(undefined)).toBeNull();
  });

  it("names the target when there is one, and the soonest when there are more", () => {
    expect(closingHeadline(plan([row()]))).toBe(
      "M 42 is on its way out of your sky — about 3 weeks left.");
    const many = closingHeadline(plan([
      row({ safe: "m_31", name: "M 31", weeks_left: 1 }),
      row(),
    ]));
    expect(many).toContain("2 of your targets");
    expect(many).toContain("M 31 first, about a week left");
  });

  it("explains the consequence in seasons, not in degrees", () => {
    expect(CLOSING_WHY).toContain("next year");
    expect(CLOSING_WHY).not.toContain("30°");
  });
});
