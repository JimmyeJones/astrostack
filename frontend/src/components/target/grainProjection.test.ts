import { describe, it, expect } from "vitest";
import {
  grainProjection,
  cardGrainProjection,
  fmtHours,
  CLEAN_SIGMA,
  GRAINY_SIGMA,
  MAX_HONEST_EXTRA_HOURS,
} from "./grainProjection";

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

  // The bug: σ is one estimate over the whole canvas, so an unevenly deep
  // mosaic can measure clean while a quarter of it is visibly grainier — and
  // the plain clean sentence then tells the reader more light buys no visible
  // cleanliness, a few centimetres under the health panel's "grain only comes
  // down with more light" about that same quarter.
  it("states the scope on an unevenly deep mosaic, so it stops contradicting the health note", () => {
    const p = grainProjection([
      { total_exposure_s: 3 * HOUR, noise_sigma: 0.016, grain_verdict: "uneven" },
    ]);
    // The verdict itself does not move: the number is honest for most of it.
    expect(p?.level).toBe("clean");
    expect(p?.moreLightFactor).toBeNull();
    // It still says what it measured, and still keeps every fact it carried.
    expect(p?.sentence).toContain("already");
    expect(p?.sentence).toContain("looks clean");
    expect(p?.sentence).toContain("3.0 h");
    expect(p?.sentence).toContain("0.016");
    expect(p?.sentence).toContain("fainter detail");
    expect(p?.sentence).toContain("29 % more");
    // …and now carries the scope plus the health note's own prescription.
    expect(p?.sentence).toContain("across most of it");
    expect(p?.sentence).toContain("thinner than the rest");
    expect(p?.sentence).toContain("only more light evens that part out");
  });

  it("keeps the plain clean wording byte-for-byte whenever nothing says uneven", () => {
    const plain = grainProjection([run(3 * HOUR, 0.016)])?.sentence;
    // An evenly covered mosaic and a single field both send null…
    expect(grainProjection([
      { total_exposure_s: 3 * HOUR, noise_sigma: 0.016, grain_verdict: null },
    ])?.sentence).toBe(plain);
    // …an older backend sends nothing at all…
    expect(grainProjection([
      { total_exposure_s: 3 * HOUR, noise_sigma: 0.016 },
    ])?.sentence).toBe(plain);
    // …and a verdict this build doesn't know is not read as "uneven".
    expect(grainProjection([
      { total_exposure_s: 3 * HOUR, noise_sigma: 0.016, grain_verdict: "flat" },
    ])?.sentence).toBe(plain);
    expect(plain).not.toContain("across most of it");
  });

  it("reads the evenness of the run it took σ from, not of some other run", () => {
    // The projection uses the *deepest* run; a shallower uneven one must not
    // put its verdict on the deep run's sentence, or the two halves of one
    // sentence describe two different pictures.
    const p = grainProjection([
      { total_exposure_s: 0.5 * HOUR, noise_sigma: 0.016, grain_verdict: "uneven" },
      { total_exposure_s: 4 * HOUR, noise_sigma: 0.016, grain_verdict: null },
    ]);
    expect(p?.hours).toBeCloseTo(4, 6);
    expect(p?.sentence).not.toContain("across most of it");
    // …and the other way round.
    const q = grainProjection([
      { total_exposure_s: 0.5 * HOUR, noise_sigma: 0.016, grain_verdict: null },
      { total_exposure_s: 4 * HOUR, noise_sigma: 0.016, grain_verdict: "uneven" },
    ]);
    expect(q?.sentence).toContain("across most of it");
  });

  it("leaves the grainy and middling wordings alone — they never contradicted the note", () => {
    // Both already prescribe more light, which is what the health note says.
    const some = grainProjection([
      { total_exposure_s: HOUR, noise_sigma: 0.04, grain_verdict: "uneven" },
    ]);
    expect(some?.sentence).toBe(grainProjection([run(HOUR, 0.04)])?.sentence);
    const grainy = grainProjection([
      { total_exposure_s: HOUR, noise_sigma: GRAINY_SIGMA, grain_verdict: "uneven" },
    ]);
    expect(grainy?.sentence).toBe(grainProjection([run(HOUR, GRAINY_SIGMA)])?.sentence);
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
