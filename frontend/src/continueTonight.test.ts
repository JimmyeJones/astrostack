import { describe, expect, it } from "vitest";
import { pickContinueTonight } from "./continueTonight";
import type { NightPlan, PlannedTarget } from "./api/client";

// Minimal PlannedTarget factory — only the fields the picker reads matter.
function target(overrides: Partial<PlannedTarget> = {}): PlannedTarget {
  return {
    id: overrides.target_safe ?? overrides.name ?? "t",
    name: "T",
    ra_deg: 0,
    dec_deg: 0,
    type: "Galaxy",
    con: "",
    already_targeted: true,
    max_altitude_deg: 60,
    transit_utc: null,
    minutes_above_min_alt: 120,
    moon_separation_deg: 90,
    score: 50,
    target_safe: "t",
    frames_accepted: 100,
    total_exposure_s: 3600,
    ...overrides,
  };
}

function plan(targets: PlannedTarget[]): NightPlan {
  return {
    location_source: "settings",
    observer: { lat_deg: 40, lon_deg: -74, elevation_m: 0 },
    generated_utc: "2026-07-24T02:00:00Z",
    dark_window: null,
    moon_illumination: 0.2,
    moon_waxing: true,
    min_altitude_deg: 30,
    horizon_active: false,
    targets,
  } as unknown as NightPlan;
}

describe("pickContinueTonight", () => {
  it("returns null for a missing or empty plan", () => {
    expect(pickContinueTonight(undefined)).toBeNull();
    expect(pickContinueTonight(null)).toBeNull();
    expect(pickContinueTonight(plan([]))).toBeNull();
  });

  it("ignores catalog (not-yet-started) and un-shootable owned targets", () => {
    const p = plan([
      target({ name: "New", target_safe: null, already_targeted: false, score: 90 }),
      target({ name: "SetLow", target_safe: "s", score: 0 }), // never clears the floor
    ]);
    expect(pickContinueTonight(p)).toBeNull();
  });

  it("recommends the owned target closest to a finished picture", () => {
    // Both Galaxies (6 h goal), both well-placed. M31 at 4.5 h (0.75) is closer
    // to its goal than M81 at 1.5 h (0.25) → M31 wins even with a lower score.
    const p = plan([
      target({ name: "M81", target_safe: "m81", total_exposure_s: 1.5 * 3600, score: 80 }),
      target({ name: "M31", target_safe: "m31", total_exposure_s: 4.5 * 3600, score: 40 }),
    ]);
    const out = pickContinueTonight(p)!;
    expect(out.pick.target.target_safe).toBe("m31");
    expect(out.runnersUp.map((r) => r.target.target_safe)).toEqual(["m81"]);
  });

  it("breaks a progress tie by tonight's observability score", () => {
    const p = plan([
      target({ name: "A", target_safe: "a", total_exposure_s: 3 * 3600, score: 30 }),
      target({ name: "B", target_safe: "b", total_exposure_s: 3 * 3600, score: 70 }),
    ]);
    const out = pickContinueTonight(p)!;
    expect(out.pick.target.target_safe).toBe("b");
  });

  it("excludes targets that already have plenty of integration", () => {
    // A Galaxy well past its 6 h goal has nothing to gain; the only improvable
    // one (still shootable) is the pick.
    const p = plan([
      target({ name: "Done", target_safe: "done", total_exposure_s: 10 * 3600, score: 90 }),
      target({ name: "Going", target_safe: "going", total_exposure_s: 2 * 3600, score: 40 }),
    ]);
    const out = pickContinueTonight(p)!;
    expect(out.pick.target.target_safe).toBe("going");
    expect(out.runnersUp).toHaveLength(0);
  });

  it("returns null when every shootable owned target is already done", () => {
    const p = plan([
      target({ name: "Done1", target_safe: "d1", total_exposure_s: 8 * 3600, score: 90 }),
      target({ name: "Done2", target_safe: "d2", total_exposure_s: 7 * 3600, score: 50 }),
    ]);
    expect(pickContinueTonight(p)).toBeNull();
  });

  it("honours a user-set integration goal over the per-type default", () => {
    // Same 2 h Galaxy: default 6 h goal → fraction 0.33 (improvable). With a
    // user goal of 2 h it's plenty (fraction 1) → excluded, leaving the other.
    const p = plan([
      target({ name: "Custom", target_safe: "c", total_exposure_s: 2 * 3600, score: 90 }),
      target({ name: "Other", target_safe: "o", total_exposure_s: 1 * 3600, score: 20 }),
    ]);
    const withDefault = pickContinueTonight(p)!;
    expect(withDefault.pick.target.target_safe).toBe("c"); // 0.33 > 0.167

    const withGoal = pickContinueTonight(p, { c: 2 * 3600 })!;
    expect(withGoal.pick.target.target_safe).toBe("o"); // "c" is now plenty → excluded
  });

  it("does NOT drop a mosaic as 'plenty' when each panel is a fraction done", () => {
    // The canonical bug from the picker's own angle: on a 2×2 mosaic 4 h
    // totalled is 1 h per panel — well *inside* what the goal is about,
    // so the picker must not treat it as done. Without ``field_fulls`` the
    // planner would have excluded it as "plenty" and told the owner to
    // point at something else the very night they were half a mosaic in.
    const p = plan([
      target({
        name: "Mosaic", target_safe: "m",
        type: "Nebula", total_exposure_s: 4 * 3600, score: 90,
        field_fulls: 4,
      }),
    ]);
    const out = pickContinueTonight(p)!;
    expect(out.pick.target.target_safe).toBe("m");
    expect(out.pick.readiness?.level).not.toBe("plenty");
    expect(out.pick.readiness?.goalHours).toBe(16);
  });

  it("does NOT drop a grown mosaic as 'plenty' against its canvas mean", () => {
    // A 2x2 for most of the time that grew into a 3x3: 7.59 fields of sky by
    // area, but the subs were shared between 31.5 typical parts. 12 h clears a
    // 1.5 h cluster goal priced by area (11.4 h) while a typical part holds
    // 23 minutes of it.
    const grown = {
      name: "Grown", target_safe: "g", type: "Cluster",
      total_exposure_s: 12 * 3600, score: 90, field_fulls: 7.587962962962963,
    };
    expect(pickContinueTonight(plan([target(grown)]))).toBeNull();
    const out = pickContinueTonight(plan([target({ ...grown, depth_fulls: 31.5 })]))!;
    expect(out.pick.target.target_safe).toBe("g");
    expect(out.pick.readiness?.goalHours).toBeCloseTo(47.25, 5);
  });

  it("caps the runners-up list", () => {
    const p = plan([
      target({ name: "A", target_safe: "a", total_exposure_s: 4 * 3600 }),
      target({ name: "B", target_safe: "b", total_exposure_s: 3 * 3600 }),
      target({ name: "C", target_safe: "c", total_exposure_s: 2 * 3600 }),
      target({ name: "D", target_safe: "d", total_exposure_s: 1 * 3600 }),
    ]);
    const out = pickContinueTonight(p, undefined, 2)!;
    expect(out.pick.target.target_safe).toBe("a");
    expect(out.runnersUp).toHaveLength(2);
    expect(out.runnersUp.map((r) => r.target.target_safe)).toEqual(["b", "c"]);
  });
  it("skips a target the adjacent 'Point here right now' card already named", () => {
    // Both Dashboard cards rank the same owned library by different rules, so
    // they routinely landed on the same target and it was printed twice, one
    // card apart. Excluding it moves this card down to the next-best target
    // rather than blanking it out.
    const p = plan([
      target({ name: "A", target_safe: "a", total_exposure_s: 4 * 3600 }),
      target({ name: "B", target_safe: "b", total_exposure_s: 3 * 3600 }),
    ]);
    expect(pickContinueTonight(p)!.pick.target.target_safe).toBe("a");
    const out = pickContinueTonight(p, undefined, 2, ["a"])!;
    expect(out.pick.target.target_safe).toBe("b");
    expect(out.runnersUp).toHaveLength(0);
  });

  it("returns null when every improvable target is already recommended", () => {
    // One started target, already named by the sibling card: say nothing rather
    // than repeat it. The Dashboard is simply one card shorter.
    const p = plan([target({ name: "A", target_safe: "a", total_exposure_s: 4 * 3600 })]);
    expect(pickContinueTonight(p, undefined, 2, ["a"])).toBeNull();
  });

  it("calls a target done when its vetted difficulty says it is", () => {
    // An easy galaxy at 4 h is past its 3 h goal — "plenty", nothing left to
    // gain, so this card must not recommend continuing it. Fails before: the
    // picker judged it against the coarse 6 h bucket and offered it anyway,
    // one screen away from a Target page calling the same picture finished.
    const p = plan([
      target({ name: "A", target_safe: "a", total_exposure_s: 4 * 3600 }),
    ]);
    const easy = { level: "easy", label: "Easy", text: "", curated: true } as const;
    expect(pickContinueTonight(p, undefined, 2, null, { a: easy })).toBeNull();
    // …and without the verdict it is still the pick it always was.
    expect(pickContinueTonight(p, undefined, 2, null)!.pick.target.target_safe)
      .toBe("a");
    // A verdict from the cluster type rule changes nothing either.
    expect(pickContinueTonight(p, undefined, 2, null,
                               { a: { ...easy, curated: false } })!
      .pick.target.target_safe).toBe("a");
  });

  it("is unchanged when nothing has been recommended yet", () => {
    // The older-backend / still-loading path: no exclusions must reproduce the
    // pre-existing pick exactly, for undefined, null and an empty list alike.
    const p = plan([
      target({ name: "A", target_safe: "a", total_exposure_s: 4 * 3600 }),
      target({ name: "B", target_safe: "b", total_exposure_s: 3 * 3600 }),
    ]);
    for (const shown of [undefined, null, []]) {
      const out = pickContinueTonight(p, undefined, 2, shown)!;
      expect(out.pick.target.target_safe).toBe("a");
      expect(out.runnersUp.map((r) => r.target.target_safe)).toEqual(["b"]);
    }
  });

  describe("a target whose window tonight has already closed", () => {
    // `/tonight` scores the whole dark window, so in the small hours a target
    // that set at 21:16 still carries score > 0. Read at 04:14 it is not
    // somewhere to point the scope "tonight".
    const NOW = Date.parse("2026-07-24T04:14:00Z");
    const gone = target({
      name: "Gone", target_safe: "gone", total_exposure_s: 5 * 3600,
      usable_start_utc: "2026-07-23T18:41:00Z", usable_end_utc: "2026-07-23T21:16:00Z",
    });
    const up = target({
      name: "Up", target_safe: "up", total_exposure_s: 1 * 3600,
      usable_start_utc: "2026-07-24T00:12:00Z", usable_end_utc: "2026-07-24T05:05:00Z",
    });
    const later = target({
      name: "Later", target_safe: "later", total_exposure_s: 0.5 * 3600,
      usable_start_utc: "2026-07-24T04:30:00Z", usable_end_utc: "2026-07-24T05:05:00Z",
    });

    it("is neither the pick nor a runner-up", () => {
      const out = pickContinueTonight(plan([gone, up, later]), undefined, 2, null,
                                      undefined, NOW)!;
      expect(out.pick.target.target_safe).toBe("up");
      expect(out.runnersUp.map((r) => r.target.target_safe)).toEqual(["later"]);
    });

    it("hides the card when every started target has already set", () => {
      expect(pickContinueTonight(plan([gone]), undefined, 2, null, undefined, NOW))
        .toBeNull();
    });

    it("counts a window ending exactly now as over", () => {
      const edge = target({ target_safe: "edge", usable_end_utc: "2026-07-24T04:14:00Z" });
      expect(pickContinueTonight(plan([edge]), undefined, 2, null, undefined, NOW))
        .toBeNull();
    });

    it("keeps today's pick when the clock or the window is unknown", () => {
      // No clock passed (older callers): nothing filtered, the deepest still wins.
      expect(pickContinueTonight(plan([gone, up]))!.pick.target.target_safe)
        .toBe("gone");
      for (const bad of [null, undefined, Number.NaN]) {
        expect(pickContinueTonight(plan([gone, up]), undefined, 2, null, undefined,
                                   bad)!.pick.target.target_safe).toBe("gone");
      }
      // No window on the row (an older backend): never hidden on a guess.
      const bare = target({ target_safe: "bare", total_exposure_s: 5 * 3600 });
      expect(pickContinueTonight(plan([bare]), undefined, 2, null, undefined, NOW)!
        .pick.target.target_safe).toBe("bare");
      const junk = target({ target_safe: "junk", usable_end_utc: "not a time" });
      expect(pickContinueTonight(plan([junk]), undefined, 2, null, undefined, NOW)!
        .pick.target.target_safe).toBe("junk");
    });
  });
});
