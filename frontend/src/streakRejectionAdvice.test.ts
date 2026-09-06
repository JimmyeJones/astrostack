import { describe, expect, it } from "vitest";
import { streakRejectionAdvice } from "./streakRejectionAdvice";
import type { StackEstimate } from "./api/client";

type Reach = NonNullable<StackEstimate["rejection_reach"]>;
type Best = NonNullable<Reach["best_available"]>;

const reach = (best: Partial<Best> | null, over: Partial<Reach> = {}): Reach => ({
  method: "mean",
  n_frames: 6,
  lone_outlier_min_frames: null,
  reaches: false,
  best_available: best === null ? null : {
    method: "min-max-reject", lone_outlier_min_frames: 3, reaches: true, ...best,
  },
  ...over,
});

// Rejection deliberately switched off — this helper's whole subject.
const noRejection = { sigma_clip: false };

describe("streakRejectionAdvice", () => {
  it("offers Auto outlier removal when some method could take the trail out", () => {
    const advice = streakRejectionAdvice({
      streaked: 2, reach: reach({}), values: noRejection,
    });
    expect(advice).not.toBeNull();
    expect(advice!.text).toContain("2 accepted frames have");
    expect(advice!.text).toContain("Auto outlier removal");
    expect(advice!.fix).toEqual({
      key: "auto_reject", label: "Turn on Auto outlier removal",
    });
  });

  it("names a method that works at the depth, never sigma clipping", () => {
    // The regression: the hand-written predicate this replaced always offered
    // "Turn on sigma clipping", which is blind to a lone trail below ~11 subs —
    // the same untruth v0.323.1 and v0.334.1 removed from two other surfaces.
    const advice = streakRejectionAdvice({
      streaked: 1, reach: reach({}), values: noRejection,
    });
    expect(advice!.text.toLowerCase()).not.toContain("sigma clip");
    expect(advice!.fix!.key).toBe("auto_reject");
  });

  it("offers nothing when no setting could reach at this sub count", () => {
    // 2 subs: under min/max's own 3-frame floor, so every button on the form
    // would swap no rejection for no rejection.
    const advice = streakRejectionAdvice({
      streaked: 1,
      reach: reach({ method: "mean", lone_outlier_min_frames: null, reaches: false },
                   { n_frames: 2 }),
      values: noRejection,
    });
    expect(advice!.fix).toBeNull();
    expect(advice!.text).toContain("Reject those frames on the Target page");
    expect(advice!.text.toLowerCase()).not.toContain("turn on");
  });

  it("names the sub count a thin stack needs when the engine knows it", () => {
    const advice = streakRejectionAdvice({
      streaked: 3,
      reach: reach({ method: "drizzle", lone_outlier_min_frames: 11, reaches: false }),
      values: { drizzle: true, drizzle_reject: false },
    });
    expect(advice!.text).toContain("about 11 subs");
    expect(advice!.fix).toBeNull();
  });

  it("offers drizzle's own rejection on the drizzle path", () => {
    const advice = streakRejectionAdvice({
      streaked: 1,
      reach: reach({ method: "drizzle", lone_outlier_min_frames: 11, reaches: true }),
      values: { drizzle: true, drizzle_reject: false },
    });
    expect(advice!.fix).toEqual({
      key: "drizzle_reject", label: "Turn on drizzle outlier rejection",
    });
    expect(advice!.text).not.toContain("Auto outlier removal");
  });

  it("stays quiet when the user did ask for rejection — that is the sibling nudge's case", () => {
    // Every toggle the normal path honours, one at a time: whether or not the
    // pick reaches, `rejectionReachNudge` owns the sentence, so the two can
    // never stack a second alert on one stack.
    for (const values of [{ sigma_clip: true }, { auto_reject: true },
                          { min_max_reject: true }]) {
      expect(streakRejectionAdvice({ streaked: 2, reach: reach({}), values }))
        .toBeNull();
    }
    // …and on the drizzle path it is drizzle's own toggle that counts, not the
    // three it overrides.
    expect(streakRejectionAdvice({
      streaked: 2,
      reach: reach({ method: "drizzle" }),
      values: { drizzle: true, drizzle_reject: true },
    })).toBeNull();
    expect(streakRejectionAdvice({
      streaked: 2,
      reach: reach({ method: "drizzle" }),
      values: { drizzle: true, sigma_clip: true },
    })).not.toBeNull();
  });

  it("stays quiet with no streaked frames, and with no answer to go on", () => {
    expect(streakRejectionAdvice({
      streaked: 0, reach: reach({}), values: noRejection,
    })).toBeNull();
    expect(streakRejectionAdvice({
      streaked: 2, reach: undefined, values: noRejection,
    })).toBeNull();
    // An older backend carries `rejection_reach` without `best_available`;
    // saying nothing beats guessing at the floor.
    expect(streakRejectionAdvice({
      streaked: 2, reach: reach(null), values: noRejection,
    })).toBeNull();
  });
});
