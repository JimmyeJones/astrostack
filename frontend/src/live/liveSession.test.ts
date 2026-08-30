import { describe, expect, it } from "vitest";
import {
  SAME_NIGHT_HOURS, alsoActiveTonight, conditionsCause, conditionsLine,
  freshnessLine, goalLine, mostRecentlyActive, sharpnessLine, tonightHeadline,
} from "./liveSession";
import type { LiveSession, Target } from "../api/client";

function live(over: Partial<LiveSession> = {}): LiveSession {
  return {
    active: true,
    n_frames: 143,
    n_kept: 118,
    n_set_aside: 25,
    kept_exposure_s: 118 * 60,
    session_exposure_s: 143 * 60,
    total_kept_exposure_s: 118 * 60,
    start_utc: "2026-07-08T21:00:00+00:00",
    latest_utc: "2026-07-08T23:29:00+00:00",
    minutes_since_latest: 1,
    conditions: {
      verdict: "good", n_recent: 20, n_recent_kept: 19,
      median_fwhm_px: null, recent_buckets: {},
    },
    reject_buckets: {},
    newest_kept_frame_id: 4242,
    goal_exposure_s: null,
    ...over,
  };
}

function target(over: Partial<Target> = {}): Target {
  return {
    safe_name: "M_42", name: "M 42", ra_deg: 83.8, dec_deg: -5.4,
    n_frames: 10, n_frames_accepted: 9, total_exposure_s: 90,
    last_activity_utc: "2026-07-08T23:00:00+00:00",
    has_preview: true, notes: null, tags: [],
    ...over,
  };
}

describe("tonightHeadline", () => {
  it("says what you've got tonight in the order you'd say it out loud", () => {
    expect(tonightHeadline(live())).toBe("143 subs so far · 118 kept · 2.0 h");
  });

  it("reads naturally for a single sub, and omits an integration of nothing", () => {
    expect(tonightHeadline(live({
      n_frames: 1, n_kept: 0, kept_exposure_s: 0,
    }))).toBe("1 sub so far · 0 kept");
  });
});

describe("conditionsLine", () => {
  it("carries the numbers behind the verdict, not just an adjective", () => {
    expect(conditionsLine(live())).toBe("Going well — 19 of your last 20 subs were kept.");
  });

  it("names a patchy stretch without scolding", () => {
    expect(conditionsLine(live({
      conditions: { verdict: "mixed", n_recent: 20, n_recent_kept: 13,
                    median_fwhm_px: null, recent_buckets: {} },
    }))).toBe("A bit patchy — 13 of your last 20 subs were kept.");
  });

  it("says plainly when something is going wrong out there", () => {
    expect(conditionsLine(live({
      conditions: { verdict: "poor", n_recent: 20, n_recent_kept: 4,
                    median_fwhm_px: null, recent_buckets: {} },
    }))).toContain("only 4 of your last 20 subs were kept");
  });

  it("treats too-few-subs as unmeasured, never as bad", () => {
    // The distinction that matters: a night three subs old is not going badly.
    const line = conditionsLine(live({
      conditions: { verdict: "unknown", n_recent: 3, n_recent_kept: 3,
                    median_fwhm_px: null, recent_buckets: {} },
    }));
    expect(line).toContain("not enough yet to tell");
    expect(line).not.toMatch(/wrong|off|patchy/);
  });

  it("says nothing has arrived when nothing has", () => {
    expect(conditionsLine(live({
      conditions: { verdict: "unknown", n_recent: 0, n_recent_kept: 0,
                    median_fwhm_px: null, recent_buckets: {} },
    }))).toBe("No subs in yet.");
  });
});

describe("conditionsCause", () => {
  it("names the dominant cause, with the action where there is one", () => {
    expect(conditionsCause(live({
      conditions: { verdict: "poor", n_recent: 20, n_recent_kept: 4,
                    median_fwhm_px: null, recent_buckets: { cloudy: 16 } },
    }))).toBe("Mostly cloud.");
    expect(conditionsCause(live({
      conditions: { verdict: "poor", n_recent: 20, n_recent_kept: 5,
                    median_fwhm_px: null, recent_buckets: { trailed: 15 } },
    }))).toContain("check the mount is tracking");
  });

  it("stays silent when nothing was set aside", () => {
    expect(conditionsCause(live())).toBeNull();
  });

  it("stays silent rather than calling a plurality 'mostly'", () => {
    // 4/10 is not "mostly" anything — saying so would be a guess.
    expect(conditionsCause(live({
      conditions: { verdict: "poor", n_recent: 20, n_recent_kept: 10,
                    median_fwhm_px: null,
                    recent_buckets: { cloudy: 4, trailed: 3, soft: 3 } },
    }))).toBeNull();
  });
});

describe("sharpnessLine", () => {
  it("quotes star size when it was measured", () => {
    expect(sharpnessLine(live({
      conditions: { verdict: "good", n_recent: 20, n_recent_kept: 19,
                    median_fwhm_px: 3.24, recent_buckets: {} },
    }))).toBe("Stars are averaging 3.2 px across tonight's keepers.");
  });

  it("says nothing when nothing was measured — never a zero", () => {
    expect(sharpnessLine(live())).toBeNull();
    expect(sharpnessLine(live({
      conditions: { verdict: "good", n_recent: 20, n_recent_kept: 19,
                    median_fwhm_px: 0, recent_buckets: {} },
    }))).toBeNull();
  });
});

describe("goalLine", () => {
  it("answers 'have I got enough to go inside?' against the whole picture", () => {
    // Measured against total kept integration, not tonight's alone: the goal is
    // for the picture, and that's the question actually being asked.
    expect(goalLine(live({
      total_kept_exposure_s: 4 * 3600, goal_exposure_s: 6 * 3600,
    }))).toBe("4.0 h of your 6.0 h goal — about 2.0 h to go.");
  });

  it("says you can stop once the goal is met", () => {
    expect(goalLine(live({
      total_kept_exposure_s: 6.5 * 3600, goal_exposure_s: 6 * 3600,
    }))).toContain("you can call it a night");
  });

  it("invents no goal when none is set", () => {
    expect(goalLine(live())).toBeNull();
    expect(goalLine(live({ goal_exposure_s: 0 }))).toBeNull();
    expect(goalLine(live({ goal_exposure_s: Number.NaN }))).toBeNull();
  });
});

describe("freshnessLine", () => {
  it("says a sub just landed", () => {
    expect(freshnessLine(live({ minutes_since_latest: 0.4 })))
      .toBe("Newest sub just landed.");
  });

  it("counts the minutes on a live but quiet stretch", () => {
    expect(freshnessLine(live({ minutes_since_latest: 12.4 })))
      .toBe("Newest sub 12 min ago.");
  });

  it("admits a finished session rather than pretending it's still going", () => {
    expect(freshnessLine(live({ active: false, minutes_since_latest: 400 })))
      .toContain("looks finished");
  });

  it("handles a session with no readable stamp at all", () => {
    expect(freshnessLine(live({ minutes_since_latest: null })))
      .toBe("Waiting for the first sub.");
  });
});

describe("mostRecentlyActive", () => {
  it("opens on the target whose frames arrived most recently", () => {
    // Zero navigation is the point: on a capture night this is the one filling up.
    const picked = mostRecentlyActive([
      target({ safe_name: "OLD", last_activity_utc: "2026-01-01T00:00:00+00:00" }),
      target({ safe_name: "NOW", last_activity_utc: "2026-07-08T23:00:00+00:00" }),
      target({ safe_name: "MID", last_activity_utc: "2026-06-01T00:00:00+00:00" }),
    ]);
    expect(picked?.safe_name).toBe("NOW");
  });

  it("ignores targets with no activity stamp, and unparseable ones", () => {
    expect(mostRecentlyActive([
      target({ safe_name: "NONE", last_activity_utc: null }),
      target({ safe_name: "JUNK", last_activity_utc: "not-a-date" }),
      target({ safe_name: "REAL", last_activity_utc: "2026-02-02T00:00:00+00:00" }),
    ])?.safe_name).toBe("REAL");
  });

  it("picks nothing rather than picking arbitrarily", () => {
    expect(mostRecentlyActive([])).toBeNull();
    expect(mostRecentlyActive(null)).toBeNull();
    expect(mostRecentlyActive(undefined)).toBeNull();
    expect(mostRecentlyActive([target({ last_activity_utc: null })])).toBeNull();
  });
});

describe("alsoActiveTonight", () => {
  const at = (safe: string, iso: string | null) =>
    target({ safe_name: safe, name: safe, last_activity_utc: iso });
  const REF = "2026-07-08T23:29:00+00:00";

  it("names the other targets from the same night, newest first", () => {
    const found = alsoActiveTonight([
      at("A", REF),
      at("B", "2026-07-08T21:40:00+00:00"),
      at("C", "2026-07-09T01:10:00+00:00"),
    ], "A");
    expect(found.map((t) => t.safe_name)).toEqual(["C", "B"]);
  });

  it("leaves out last week's session, the current target, and unstamped ones", () => {
    const found = alsoActiveTonight([
      at("A", REF),
      at("OLD", "2026-01-01T00:00:00+00:00"),
      at("NEVER", null),
      at("JUNK", "not a date"),
    ], "A");
    expect(found).toEqual([]);
  });

  it("uses the window either side of the target on screen", () => {
    const justInside = new Date(
      Date.parse(REF) - (SAME_NIGHT_HOURS - 0.5) * 3600_000).toISOString();
    const justOutside = new Date(
      Date.parse(REF) - (SAME_NIGHT_HOURS + 0.5) * 3600_000).toISOString();
    expect(alsoActiveTonight([at("A", REF), at("IN", justInside)], "A")
      .map((t) => t.safe_name)).toEqual(["IN"]);
    expect(alsoActiveTonight([at("A", REF), at("OUT", justOutside)], "A"))
      .toEqual([]);
  });

  it("caps the list rather than becoming a second dashboard", () => {
    const many = [at("A", REF)];
    for (let i = 0; i < 6; i += 1) {
      many.push(at(`T${i}`, new Date(Date.parse(REF) - i * 600_000).toISOString()));
    }
    expect(alsoActiveTonight(many, "A")).toHaveLength(3);
  });

  it("says nothing when there is nothing to say", () => {
    expect(alsoActiveTonight(null, "A")).toEqual([]);
    expect(alsoActiveTonight([at("A", REF)], "A")).toEqual([]);
    // No stamp on the target being watched ⇒ no window to compare against.
    expect(alsoActiveTonight([at("A", null), at("B", REF)], "A")).toEqual([]);
    expect(alsoActiveTonight([at("A", REF)], null)).toEqual([]);
  });
});
