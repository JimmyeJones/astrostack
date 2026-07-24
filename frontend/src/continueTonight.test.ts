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
});
