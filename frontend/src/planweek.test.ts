import { describe, expect, it } from "vitest";

import type { PlanWeek, TargetBestNight, WeekNight } from "./api/client";
import {
  bestNightOfWeek, otherTargetNights, targetNightPhrase, weekEmptyReason,
  weekHeadline, weekMoonNote, weekNightLabel, weekNightLabelInline,
} from "./planweek";

// A Wednesday evening, so the weekday labels below are unambiguous.
const NOW = new Date("2026-09-02T20:00:00");

function night(over: Partial<WeekNight> & { date: string }): WeekNight {
  return {
    dark_start_utc: `${over.date}T20:30:00+00:00`,
    dark_end_utc: `${over.date}T04:30:00+00:00`,
    dark_minutes: 480,
    moon_illumination: 0.1,
    n_usable: 1,
    best: null,
    ...over,
  };
}

function pick(over: Partial<NonNullable<WeekNight["best"]>> = {}) {
  return {
    safe: "M_31", name: "M 31",
    usable_start_utc: "2026-09-04T21:00:00+00:00",
    usable_end_utc: "2026-09-05T01:00:00+00:00",
    minutes_above_min_alt: 246,
    max_altitude_deg: 61.2,
    moon_up_fraction: 0.0,
    score: 71.0,
    ...over,
  };
}

function plan(over: Partial<PlanWeek> = {}): PlanWeek {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    generated_utc: "2026-09-02T20:00:00+00:00",
    min_altitude_deg: 30,
    horizon_active: false,
    nights_scanned: 7,
    nights: [],
    targets: [],
    n_targets_considered: 2,
    n_targets_with_position: 2,
    ...over,
  };
}

describe("weekNightLabel", () => {
  it("names tonight, tomorrow, then the weekday", () => {
    expect(weekNightLabel("2026-09-02", NOW)).toBe("Tonight");
    expect(weekNightLabel("2026-09-03", NOW)).toBe("Tomorrow");
    expect(weekNightLabel("2026-09-05", NOW)).toBe("Saturday");
    expect(weekNightLabel("2026-09-08", NOW)).toBe("Tuesday");
  });

  it("dates a night far enough out that a bare weekday would be ambiguous", () => {
    // Seven days on is the *same* weekday as today — "Wednesday" would be a lie.
    expect(weekNightLabel("2026-09-09", NOW)).toContain("Sep");
    expect(weekNightLabel("2026-09-09", NOW)).toContain("9");
  });

  it("still says Tonight in the small hours of the night that began yesterday", () => {
    // 00:30 on the 3rd: the user is inside the night labelled by the 2nd.
    const smallHours = new Date("2026-09-03T00:30:00");
    expect(weekNightLabel("2026-09-02", smallHours)).toBe("Tonight");
    expect(weekNightLabel("2026-09-03", smallHours)).toBe("Tonight");
  });

  it("passes a malformed date straight through rather than inventing a day", () => {
    expect(weekNightLabel("not-a-date", NOW)).toBe("not-a-date");
  });

  it("lower-cases only the relative labels for mid-sentence use", () => {
    expect(weekNightLabelInline("2026-09-02", NOW)).toBe("tonight");
    expect(weekNightLabelInline("2026-09-03", NOW)).toBe("tomorrow");
    expect(weekNightLabelInline("2026-09-05", NOW)).toBe("Saturday");
  });
});

describe("bestNightOfWeek", () => {
  it("picks the highest-scoring night", () => {
    const nights = [
      night({ date: "2026-09-02", best: pick({ score: 40 }) }),
      night({ date: "2026-09-04", best: pick({ score: 80 }) }),
      night({ date: "2026-09-05", best: pick({ score: 60 }) }),
    ];
    expect(bestNightOfWeek(nights)?.date).toBe("2026-09-04");
  });

  it("breaks a tie towards the sooner night — go out on the first one", () => {
    const nights = [
      night({ date: "2026-09-03", best: pick({ score: 80 }) }),
      night({ date: "2026-09-06", best: pick({ score: 80 }) }),
    ];
    expect(bestNightOfWeek(nights)?.date).toBe("2026-09-03");
  });

  it("ignores nights with nothing placed, and returns null when none are", () => {
    expect(bestNightOfWeek([night({ date: "2026-09-02" })])).toBeNull();
    expect(bestNightOfWeek([])).toBeNull();
    const mixed = [night({ date: "2026-09-02" }),
                   night({ date: "2026-09-03", best: pick({ score: 10 }) })];
    expect(bestNightOfWeek(mixed)?.date).toBe("2026-09-03");
  });
});

describe("weekHeadline", () => {
  it("names the night, the target and how long it is up", () => {
    const p = plan({ nights: [night({ date: "2026-09-05", best: pick() })] });
    expect(weekHeadline(p, NOW)).toBe(
      "Your best night is Saturday — M 31, 4.1 h above 30°.");
  });

  it("says minutes rather than a misleading 0.6 h for a short window", () => {
    const p = plan({
      nights: [night({ date: "2026-09-03",
                       best: pick({ minutes_above_min_alt: 50 }) })],
    });
    expect(weekHeadline(p, NOW)).toContain("50 min");
  });

  it("is null when nothing is placed — the card must not invent a night", () => {
    expect(weekHeadline(plan(), NOW)).toBeNull();
    expect(weekHeadline(plan({ nights: [night({ date: "2026-09-02" })] }), NOW))
      .toBeNull();
  });
});

describe("weekEmptyReason", () => {
  it("is null whenever there is something to show", () => {
    const p = plan({ nights: [night({ date: "2026-09-05", best: pick() })] });
    expect(weekEmptyReason(p)).toBeNull();
  });

  it("names the fix for each way of being empty", () => {
    expect(weekEmptyReason(plan({ location_source: "none" })))
      .toContain("observing location");
    expect(weekEmptyReason(plan({ n_targets_with_position: 0 })))
      .toContain("plate-solve");
    expect(weekEmptyReason(plan({ nights: [] }))).toContain("no real darkness");
    // Nights exist and targets exist, but nothing clears the floor.
    expect(weekEmptyReason(plan({
      nights: [night({ date: "2026-09-02", n_usable: 0 })], min_altitude_deg: 50,
    }))).toContain("50°");
  });
});

describe("otherTargetNights", () => {
  const targets: TargetBestNight[] = [
    { safe: "M_31", name: "M 31", date: "2026-09-05", minutes_above_min_alt: 246, score: 71 },
    { safe: "M_42", name: "M 42", date: "2026-09-06", minutes_above_min_alt: 130, score: 44 },
    { safe: "M_13", name: "M 13", date: "2026-09-07", minutes_above_min_alt: 120, score: 40 },
  ];

  it("drops the target the headline already named on that night", () => {
    const p = plan({
      nights: [night({ date: "2026-09-05", best: pick() })],
      targets,
    });
    expect(otherTargetNights(p).map((t) => t.safe)).toEqual(["M_42", "M_13"]);
  });

  it("keeps the same target when its own best night is a different one", () => {
    const p = plan({
      nights: [night({ date: "2026-09-06", best: pick({ score: 90 }) })],
      targets,
    });
    // The headline named M 31 on the 6th; M 31's *own* best night is the 5th, so
    // that row still says something new.
    expect(otherTargetNights(p).map((t) => t.safe)).toEqual(
      ["M_31", "M_42", "M_13"]);
  });

  it("caps the list so a big library doesn't become a wall", () => {
    const many = Array.from({ length: 12 }, (_v, i) => ({
      safe: `T${i}`, name: `T ${i}`, date: "2026-09-05",
      minutes_above_min_alt: 100, score: 10,
    }));
    expect(otherTargetNights(plan({ targets: many }))).toHaveLength(4);
    expect(otherTargetNights(plan({ targets: many }), 2)).toHaveLength(2);
  });

  it("phrases a row as name — night", () => {
    expect(targetNightPhrase(targets[0], NOW)).toBe("M 31 — Saturday");
  });
});

describe("weekMoonNote", () => {
  it("stays silent when the Moon is down, even at full", () => {
    expect(weekMoonNote(night({
      date: "2026-09-05", moon_illumination: 1.0,
      best: pick({ moon_up_fraction: 0.0 }),
    }))).toBeNull();
  });

  it("stays silent for a thin crescent that is up", () => {
    expect(weekMoonNote(night({
      date: "2026-09-05", moon_illumination: 0.2,
      best: pick({ moon_up_fraction: 1.0 }),
    }))).toBeNull();
  });

  it("warns when a bright Moon really is in the sky, and says for how much of it", () => {
    expect(weekMoonNote(night({
      date: "2026-09-05", moon_illumination: 0.85,
      best: pick({ moon_up_fraction: 1.0 }),
    }))).toBe("Moon 85%, up all night");
    expect(weekMoonNote(night({
      date: "2026-09-05", moon_illumination: 0.6,
      best: pick({ moon_up_fraction: 0.5 }),
    }))).toBe("Moon 60%, up part of the night");
  });

  it("is silent when the fraction is unknown or the night is unplaced", () => {
    expect(weekMoonNote(night({
      date: "2026-09-05", moon_illumination: 0.9,
      best: pick({ moon_up_fraction: null }),
    }))).toBeNull();
    expect(weekMoonNote(night({ date: "2026-09-05", moon_illumination: 0.9 })))
      .toBeNull();
  });
});
