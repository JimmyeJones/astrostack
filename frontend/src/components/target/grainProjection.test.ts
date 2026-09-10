import { describe, it, expect } from "vitest";
import {
  grainProjection,
  cardGrainProjection,
  fmtHours,
  CLEAN_SIGMA,
  GRAINY_SIGMA,
  MAX_HONEST_EXTRA_HOURS,
  IDEAL_EXPONENT,
} from "./grainProjection";
import { integrationTrend } from "./integrationTrend";

// Minimal run shape: the helper only reads integration, measured σ, and the
// genuine-run flag.
const run = (
  t_s: number | null,
  sigma: number | null,
  reusable?: boolean,
) => ({ total_exposure_s: t_s, noise_sigma: sigma, reusable });

const HOUR = 3600;

describe("grainProjection", () => {
  it("says nothing without a genuine measured stack", () => {
    expect(grainProjection(null)).toBeNull();
    expect(grainProjection(undefined)).toBeNull();
    expect(grainProjection([])).toBeNull();
    // Integration but no measured σ (a run from before the noise column).
    expect(grainProjection([run(HOUR, null)])).toBeNull();
    // A σ but no integration total.
    expect(grainProjection([run(null, 0.03)])).toBeNull();
    // Non-finite / non-positive readings are not measurements.
    expect(grainProjection([run(HOUR, 0)])).toBeNull();
    expect(grainProjection([run(HOUR, Number.NaN)])).toBeNull();
    expect(grainProjection([run(0, 0.03)])).toBeNull();
  });

  it("skips editor-export / combine runs, whose σ isn't comparable", () => {
    expect(grainProjection([run(HOUR, 0.03, false)])).toBeNull();
    // …but a genuine run alongside one still speaks, and the export is ignored
    // even though it is the deeper of the two.
    const p = grainProjection([run(10 * HOUR, 0.01, false), run(HOUR, 0.03, true)]);
    expect(p?.hours).toBeCloseTo(1, 6);
    expect(p?.sigma).toBeCloseTo(0.03, 6);
  });

  it("treats a run from an older backend (no reusable flag) as genuine", () => {
    const p = grainProjection([{ total_exposure_s: HOUR, noise_sigma: 0.03 }]);
    expect(p).not.toBeNull();
    expect(p?.hours).toBeCloseTo(1, 6);
  });

  it("reads the deepest genuine stack, not the newest", () => {
    // A later shallow re-stack of a subset isn't the picture the user judges.
    const p = grainProjection([run(0.5 * HOUR, 0.09), run(4 * HOUR, 0.025)]);
    expect(p?.hours).toBeCloseTo(4, 6);
    expect(p?.sigma).toBeCloseTo(0.025, 6);
  });

  it("calls a deep stack at the owner's own measured σ clean, and doesn't tell them to stop", () => {
    // 0.016 is inside the 0.015–0.020 band the owner's real 271–787-frame
    // stacks measured — good pictures, so this must read as clean.
    const p = grainProjection([run(3 * HOUR, 0.016)]);
    expect(p?.level).toBe("clean");
    expect(p?.moreLightFactor).toBeNull();
    expect(p?.extraHours).toBeNull();
    expect(p?.beyondReach).toBe(false);
    expect(p?.sentence).toContain("already looks clean");
    // Reconciles with the goal verdict above it rather than contradicting it:
    // more time still buys faint detail, so it never says "you're done".
    expect(p?.sentence).toContain("fainter detail");
    expect(p?.sentence).toContain("3.0 h");
    expect(p?.sentence).toContain("0.016");
  });

  it("quotes the honest 4×-light figure for a middling stack", () => {
    // σ = 0.04 is double the clean bar → (0.04/0.02)² = 4× the light, so 3×
    // more than the 1 h already there.
    const p = grainProjection([run(HOUR, 0.04)]);
    expect(p?.level).toBe("some");
    expect(p?.moreLightFactor).toBeCloseTo(4, 6);
    expect(p?.extraHours).toBeCloseTo(3, 6);
    expect(p?.sentence).toContain("4× the light");
    expect(p?.sentence).toContain("3.0 h more");
    expect(p?.sentence).toContain("little grain left");
  });

  it("calls a stack at the denoise advisor's full-strength bar grainy", () => {
    // GRAINY_SIGMA is exactly seestack/edit/noise._SIGMA_FULL — the σ at which
    // the editor already asks for its strongest denoise.
    expect(GRAINY_SIGMA).toBe(0.05);
    const p = grainProjection([run(HOUR, GRAINY_SIGMA)]);
    expect(p?.level).toBe("grainy");
    expect(p?.sentence).toContain("still grainy");
    // (0.05/0.02)² = 6.25 → rounded to 6.3× the light, 5.3 h more.
    expect(p?.moreLightFactor).toBeCloseTo(6.3, 6);
    expect(p?.extraHours).toBeCloseTo(5.3, 6);
    expect(p?.sentence).toContain("6.3× the light");
    expect(p?.sentence).toContain("square root of time");
  });

  it("puts the clean/grainy bars exactly on the documented thresholds", () => {
    expect(CLEAN_SIGMA).toBe(0.02);
    expect(grainProjection([run(HOUR, CLEAN_SIGMA)])?.level).toBe("clean");
    expect(grainProjection([run(HOUR, CLEAN_SIGMA + 0.001)])?.level).toBe("some");
    expect(grainProjection([run(HOUR, GRAINY_SIGMA - 0.001)])?.level).toBe("some");
    expect(grainProjection([run(HOUR, GRAINY_SIGMA)])?.level).toBe("grainy");
  });

  it("still quotes a big light multiple when the base is short enough to reach", () => {
    // 25× the light off a 20-minute first attempt is one long evening, not a
    // fantasy — the clamp is on the hours, not the multiple, so it must quote.
    const p = grainProjection([run(HOUR / 3, 0.1)]);
    expect(p?.beyondReach).toBe(false);
    expect(p?.moreLightFactor).toBeCloseTo(25, 6);
    expect(p?.extraHours).toBeCloseTo(8, 6);
    expect(p?.sentence).toContain("25× the light");
  });

  it("refuses to quote a number of hours no run of clear nights would deliver", () => {
    // 0.12 off an already-deep 6 h stack wants 36× the light — 210 more hours.
    const p = grainProjection([run(6 * HOUR, 0.12)]);
    expect(p?.level).toBe("grainy");
    expect(p?.beyondReach).toBe(true);
    expect(p?.moreLightFactor).toBeNull();
    expect(p?.extraHours).toBeNull();
    expect(p?.sentence).toContain("dozens more clear nights");
    // Never prints the light multiple / hours figure it just refused to stand
    // behind — no "36× the light", no "210 h more".
    expect(p?.sentence).not.toContain("×");
    expect(p?.sentence).not.toContain(" more would");
    expect(MAX_HONEST_EXTRA_HOURS).toBe(60);
  });

  it("always offers the halve-the-grain figure: 4× the light, so 3× what's there", () => {
    expect(grainProjection([run(2 * HOUR, 0.016)])?.hoursToHalve).toBeCloseTo(6, 6);
    expect(grainProjection([run(2 * HOUR, 0.09)])?.hoursToHalve).toBeCloseTo(6, 6);
  });

  it("projects along the ideal exponent when there is only one stack to read", () => {
    const p = grainProjection([run(HOUR, 0.04)]);
    expect(p?.exponent).toBeCloseTo(IDEAL_EXPONENT, 12);
    expect(p?.measuredFalloff).toBe(false);
    // No "at the rate…" clause, and the ideal doubling figure, unchanged.
    expect(p?.sentence).toContain("About 4× the light");
    expect(grainProjection([run(3 * HOUR, 0.016)])?.sentence)
      .toContain("about 29 % more");
  });

  it("quotes the target's OWN measured falloff, not the ideal, once two stacks fit one", () => {
    // 1 h @ 0.06 → 3 h @ 0.05 fits p = ln(1.2)/ln(3) ≈ 0.166: this target's noise
    // is measurably falling far slower than √t. The ideal projection says
    // (0.05/0.02)² = 6.3× the light — "roughly 16 h more". At the measured rate
    // it is 2.5^(1/0.166) ≈ 250× — about 747 h, i.e. dozens of clear nights.
    // Quoting the 16 h is a plan a beginner would actually go and shoot.
    const runs = [run(HOUR, 0.06), run(3 * HOUR, 0.05)];
    const p = grainProjection(runs);
    expect(p?.hours).toBeCloseTo(3, 6);
    expect(p?.measuredFalloff).toBe(true);
    expect(p?.exponent).toBeCloseTo(0.166, 2);
    // Fails before the fix, which quoted 6.3× / 15.6 h here.
    expect(p?.beyondReach).toBe(true);
    expect(p?.moreLightFactor).toBeNull();
    expect(p?.extraHours).toBeNull();
    expect(p?.sentence).toContain("dozens more clear nights");
    expect(p?.sentence).not.toContain("6.3×");
    expect(p?.sentence).not.toContain("16 h more");
    // …and it must not credit the target with the √t law it just failed.
    expect(p?.sentence).toContain("falling more slowly than the square root of time");
  });

  it("still quotes a figure on a measured-but-reachable target, at the measured rate", () => {
    // 20 min @ 0.05 → 40 min @ 0.043 fits p ≈ 0.218. Reaching clean needs
    // 2.5^(1/0.218) ≈ 64× the light off a 0.67 h base ≈ 42 h more — big, but
    // inside MAX_HONEST_EXTRA_HOURS, so it is still a quotable plan.
    const runs = [run(HOUR / 3, 0.05), run((2 * HOUR) / 3, 0.043)];
    const p = grainProjection(runs);
    expect(p?.measuredFalloff).toBe(true);
    expect(p?.beyondReach).toBe(false);
    // The ideal would have said 6.3× / 3.5 h more; the measured rate is far more.
    expect(p?.moreLightFactor as number).toBeGreaterThan(30);
    expect(p?.extraHours as number).toBeGreaterThan(20);
    expect(p?.extraHours as number).toBeLessThanOrEqual(MAX_HONEST_EXTRA_HOURS);
    expect(p?.sentence).toContain("At the rate this target's own stacks have been improving");
  });

  it("never promises better than shot noise when the measured exponent overshoots", () => {
    // A σ that fell faster than √t (measurement luck, or a night that was simply
    // better) fits p > 0.5. Projecting along that would quote *less* light than
    // the physics allows, which is the one direction this must never move.
    const lucky = [run(HOUR, 0.08), run(2 * HOUR, 0.04)];  // p = 1.0
    const p = grainProjection(lucky);
    expect(p?.exponent).toBeCloseTo(IDEAL_EXPONENT, 12);
    expect(p?.measuredFalloff).toBe(false);
    // Identical to the same deepest stack read on its own.
    const alone = grainProjection([run(2 * HOUR, 0.04)]);
    expect(p?.moreLightFactor).toBeCloseTo(alone?.moreLightFactor as number, 12);
    expect(p?.extraHours).toBeCloseTo(alone?.extraHours as number, 12);
  });

  it("says the same thing about doubling as the History noise-trend card", () => {
    // The one number both surfaces print for one target. Read off the trend
    // itself, so they cannot round to two different percentages.
    const runs = [run(HOUR, 0.019), run(3 * HOUR, 0.016)];
    const t = integrationTrend(runs);
    const p = grainProjection(runs);
    expect(p?.level).toBe("clean");
    expect(t).not.toBeNull();
    expect(p?.sentence).toContain(`about ${t?.percentCutIfDoubled} % more`);
  });

  it("declines the halve-the-grain figure when the noise has stopped falling", () => {
    // p ≤ 0: no multiple of the light halves this grain, so there is no number.
    const p = grainProjection([run(HOUR, 0.04), run(3 * HOUR, 0.042)]);
    expect(p?.exponent).toBeLessThanOrEqual(0);
    expect(p?.hoursToHalve).toBeNull();
    expect(p?.beyondReach).toBe(true);
    expect(p?.moreLightFactor).toBeNull();
  });
});

describe("cardGrainProjection", () => {
  it("passes a single-stack projection straight through", () => {
    const runs = [run(HOUR, 0.04)];
    expect(cardGrainProjection(runs)).toEqual(grainProjection(runs));
  });

  it("goes quiet when the target's measured trend says it has plateaued", () => {
    // Integration doubled and σ didn't move → measured exponent ~0 (sky-limited).
    // The IntegrationTrendBadge is saying "more subs won't help" on this very
    // page, so an assumed-√t "4× the light would clean it up" must not appear.
    const runs = [run(HOUR, 0.04), run(2 * HOUR, 0.04)];
    expect(grainProjection(runs)).not.toBeNull();  // it *would* have spoken
    expect(cardGrainProjection(runs)).toBeNull();
  });

  it("still speaks when the measured trend agrees the target is improving", () => {
    // σ falls as 1/√t → "improving", which the projection only reinforces.
    const runs = [run(HOUR, 0.06), run(2 * HOUR, 0.0424)];
    const p = cardGrainProjection(runs);
    expect(p).not.toBeNull();
    expect(p?.hours).toBeCloseTo(2, 6);
  });
});

describe("fmtHours", () => {
  it("reads naturally at every scale a Seestar owner sees", () => {
    expect(fmtHours(0.5)).toBe("30 min");
    expect(fmtHours(1)).toBe("1.0 h");
    expect(fmtHours(3.25)).toBe("3.3 h");
    expect(fmtHours(12.4)).toBe("12 h");
    // Never "0 min" — a sliver of time still rounds up to something real.
    expect(fmtHours(0.001)).toBe("1 min");
  });
});
