import { describe, it, expect } from "vitest";
import {
  integrationTrend,
  MIN_TIME_RATIO,
} from "./integrationTrend";
import { cardGrainProjection } from "./grainProjection";

// Minimal run shape: the helper only reads integration time + measured noise σ.
const run = (t_s: number | null, sigma: number | null) => ({
  total_exposure_s: t_s,
  noise_sigma: sigma,
});

const HOUR = 3600;

describe("integrationTrend", () => {
  it("returns null without enough measured points", () => {
    expect(integrationTrend(null)).toBeNull();
    expect(integrationTrend([])).toBeNull();
    expect(integrationTrend([run(HOUR, 1.0)])).toBeNull();
    // Two runs but only one measures a σ → not enough.
    expect(integrationTrend([run(HOUR, 1.0), run(2 * HOUR, null)])).toBeNull();
  });

  it("returns null when the two stacks don't span a real integration increase", () => {
    // ratio 1.4 < MIN_TIME_RATIO (1.5) → can't read a trend.
    expect(integrationTrend([run(HOUR, 1.0), run(1.4 * HOUR, 0.9)])).toBeNull();
    expect(MIN_TIME_RATIO).toBe(1.5);
  });

  it("calls a stack that tracks the ideal √t 'improving'", () => {
    // Time doubles, σ falls by 1/√2 ≈ 0.707 → exponent 0.5 (ideal).
    const t = integrationTrend([run(HOUR, 1.0), run(2 * HOUR, 0.707)]);
    expect(t).not.toBeNull();
    expect(t?.level).toBe("improving");
    expect(t?.exponent).toBeCloseTo(0.5, 2);
    expect(t?.hoursNow).toBeCloseTo(2.0, 3);
    expect(t?.percentCutIfDoubled).toBe(29);
  });

  it("calls a flat / rising noise trend 'plateaued'", () => {
    // Time trebles but σ doesn't move → exponent ~0 → sky-limited.
    const flat = integrationTrend([run(HOUR, 0.5), run(3 * HOUR, 0.5)]);
    expect(flat?.level).toBe("plateaued");
    expect(flat?.percentCutIfDoubled).toBe(0);
    // Noise actually rose with more time → still plateaued, never a negative promise.
    const rose = integrationTrend([run(HOUR, 0.5), run(3 * HOUR, 0.6)]);
    expect(rose?.level).toBe("plateaued");
    expect(rose?.percentCutIfDoubled).toBe(0);
  });

  it("calls a below-ideal-but-real falloff 'slowing'", () => {
    // ratio 4, σ 1.0 → 0.707 ⇒ exponent 0.25 (between plateau 0.15 and ideal 0.4).
    const t = integrationTrend([run(HOUR, 1.0), run(4 * HOUR, 0.707)]);
    expect(t?.level).toBe("slowing");
    expect(t?.exponent).toBeCloseTo(0.25, 2);
    expect(t?.percentCutIfDoubled).toBe(16);
  });

  it("reads the trend by integration time, not run order, and ignores unmeasured runs", () => {
    // Deepest stack is in the middle; a null-σ run and a null-time run are noise.
    const t = integrationTrend([
      run(2 * HOUR, 0.707),
      run(4 * HOUR, 0.5), // deepest measured (ideal √t vs the shallowest below)
      run(null, 0.4),
      run(HOUR, 1.0), // shallowest measured
    ]);
    expect(t).not.toBeNull();
    // shallow (1h, σ1.0) vs deep (4h, σ0.5): exponent ln(2)/ln(4) = 0.5 → improving.
    expect(t?.level).toBe("improving");
    expect(t?.exponent).toBeCloseTo(0.5, 2);
    expect(t?.hoursNow).toBeCloseTo(4.0, 3);
  });

  // A mosaic's canvas grows as its panels are shot, so "more total light" can
  // mean a wider picture rather than a deeper one. Reading the falloff off the
  // total told the owner — a heavy mosaic user — that a mosaic a few subs deep
  // everywhere was sky-limited and worth abandoning.
  describe("a mosaic is judged on per-pixel depth, not the target's total", () => {
    // Same run shape plus the canvas's field-fulls figure.
    const mosaicRun = (t_s: number, sigma: number, fieldFulls: number | null) => ({
      total_exposure_s: t_s,
      noise_sigma: sigma,
      field_fulls: fieldFulls,
    });

    it("says nothing about a mosaic that only got wider", () => {
      // 2x2 at 0.5 h/panel, then 3x3 at 0.5 h/panel: 2 h -> 4.5 h of total light
      // (ratio 2.25, past MIN_TIME_RATIO) and identical grain, because no pixel
      // ever got more light. Fitted on the total that reads as a plateau; fitted
      // on depth there is simply no increase to judge.
      expect(integrationTrend([
        mosaicRun(2 * HOUR, 0.030, 4),
        mosaicRun(4.5 * HOUR, 0.030, 9),
      ])).toBeNull();
    });

    it("still calls a mosaic that stopped improving at a fixed size plateaued", () => {
      // Same 2x2 canvas both times, 4x the light, grain unmoved — a real plateau,
      // and the fix must not have made the verdict unreachable on a mosaic.
      const t = integrationTrend([
        mosaicRun(2 * HOUR, 0.030, 4),
        mosaicRun(8 * HOUR, 0.030, 4),
      ]);
      expect(t?.level).toBe("plateaued");
      // The sentence still names the *total* the rest of the app prints for that
      // run (8 h), never the 2 h one pixel of it received.
      expect(t?.hoursNow).toBeCloseTo(8.0, 3);
      expect(t?.sentence).toContain("8.0 h");
    });

    it("credits a mosaic that genuinely deepened", () => {
      // 2x2 throughout: 4x the per-pixel light, grain halved — the ideal √t.
      const t = integrationTrend([
        mosaicRun(2 * HOUR, 0.030, 4),
        mosaicRun(8 * HOUR, 0.015, 4),
      ]);
      expect(t?.level).toBe("improving");
      expect(t?.exponent).toBeCloseTo(0.5, 2);
    });

    it("is exactly today's verdict when every run shares one field-fulls figure", () => {
      // The scale divides out of the ratio, so a same-size canvas — including
      // every single-field target — reads identically however it is labelled.
      const plain = integrationTrend([run(HOUR, 1.0), run(4 * HOUR, 0.707)]);
      for (const ff of [null, undefined, 0, 0.4, 1, 4]) {
        const scaled = integrationTrend([
          { total_exposure_s: HOUR, noise_sigma: 1.0, field_fulls: ff },
          { total_exposure_s: 4 * HOUR, noise_sigma: 0.707, field_fulls: ff },
        ]);
        expect(scaled?.level).toBe(plain?.level);
        expect(scaled?.exponent).toBeCloseTo(plain?.exponent as number, 10);
        expect(scaled?.hoursNow).toBeCloseTo(plain?.hoursNow as number, 10);
        expect(scaled?.sentence).toBe(plain?.sentence);
      }
    });

    describe("a plateau on a mosaic with one thinner panel", () => {
      // The fit's σ is one estimate over the whole canvas, so on an unevenly
      // deep mosaic a plateau describes the part that got the most subs. Said of
      // the picture, "more subs won't help it much" is the flat opposite of the
      // "How's my stack?" panel's own note about the same canvas ("grain only
      // comes down with more light — so another night on that panel is what
      // evens it out"), and this is the one place nothing counterbalances it:
      // `cardGrainProjection` goes silent on a plateau and the card goes on to
      // name a different target to point at instead.
      const uneven = (t_s: number, sigma: number, ff: number) => ({
        total_exposure_s: t_s, noise_sigma: sigma, field_fulls: ff,
        grain_verdict: "uneven",
      });

      it("scopes the verdict and keeps the thin part's lever", () => {
        // Fails before: the sentence was the unscoped "this target looks
        // sky-limited from here, so more subs won't help it much".
        const t = integrationTrend([
          uneven(2 * HOUR, 0.030, 4), uneven(8 * HOUR, 0.030, 4),
        ]);
        expect(t?.level).toBe("plateaued");
        expect(t?.unevenDepth).toBe(true);
        expect(t?.sentence).toContain("Across the deepest part of this picture");
        expect(t?.sentence).toContain("thinner than the rest");
        // It must still say the thin part responds to light — the health note's
        // own claim — and must not tell the owner more subs won't help at all.
        expect(t?.sentence).toContain("comes down with more light");
        expect(t?.sentence).not.toContain("more subs won't help it much");
        // …and the two levers survive, in order rather than instead.
        expect(t?.sentence).toContain("another pass over it");
        expect(t?.sentence).toContain("After that, a darker sky or a brighter target");
        // The measurement is untouched: same hours, same exponent as the even
        // mosaic of identical depth.
        const even = integrationTrend([
          mosaicRun(2 * HOUR, 0.030, 4), mosaicRun(8 * HOUR, 0.030, 4),
        ]);
        expect(t?.hoursNow).toBeCloseTo(even?.hoursNow as number, 10);
        expect(t?.exponent).toBeCloseTo(even?.exponent as number, 10);
        expect(t?.percentCutIfDoubled).toBe(even?.percentCutIfDoubled);
      });

      it("reads the verdict off the deepest run, not off any run", () => {
        // The sentence is about the deepest picture, so an *older*, shallower run
        // that happened to be uneven must not scope a verdict about a canvas that
        // has since evened out — and vice versa.
        const deepEvenly = integrationTrend([
          uneven(2 * HOUR, 0.030, 4), mosaicRun(8 * HOUR, 0.030, 4),
        ]);
        expect(deepEvenly?.level).toBe("plateaued");
        expect(deepEvenly?.unevenDepth).toBe(false);
        expect(deepEvenly?.sentence).toContain("more subs won't help it much");
      });

      it("leaves every other verdict and every other value alone", () => {
        // Only the plateau branch reads it: an improving or slowing mosaic
        // already prescribes more time, so its wording is unchanged…
        // 4x the light: σ 0.015 is the ideal √t ("improving"), σ 0.0212 is
        // exponent ≈ 0.25 ("slowing").
        for (const sigma of [0.015, 0.0212]) {
          const a = integrationTrend([
            uneven(2 * HOUR, 0.030, 4), uneven(8 * HOUR, sigma, 4),
          ]);
          const b = integrationTrend([
            mosaicRun(2 * HOUR, 0.030, 4), mosaicRun(8 * HOUR, sigma, 4),
          ]);
          expect(a?.level).not.toBe("plateaued");
          expect(a?.sentence).toBe(b?.sentence);
        }
        // …and so is every shape of "no verdict", including a measured one that
        // is not "uneven" (a flat/checked seam says nothing about depth).
        const base = integrationTrend([
          mosaicRun(2 * HOUR, 0.030, 4), mosaicRun(8 * HOUR, 0.030, 4),
        ]);
        for (const v of [null, undefined, "", "flat", "check"]) {
          expect(integrationTrend([
            { total_exposure_s: 2 * HOUR, noise_sigma: 0.030, field_fulls: 4,
              grain_verdict: v },
            { total_exposure_s: 8 * HOUR, noise_sigma: 0.030, field_fulls: 4,
              grain_verdict: v },
          ])).toEqual(base);
        }
      });

      it("still lets cardGrainProjection defer to the plateau", () => {
        // The two cards' division of labour is gated on the *level*, which none
        // of this touches — so the projection still stands aside here, and the
        // scoped sentence is genuinely the only thing counterbalancing the
        // health note rather than a second opinion beside a third.
        const runs = [uneven(2 * HOUR, 0.030, 4), uneven(8 * HOUR, 0.030, 4)];
        expect(integrationTrend(runs)?.level).toBe("plateaued");
        expect(cardGrainProjection(runs)).toBeNull();
      });
    });

    it("picks the deepest run by depth, and still names that run's total", () => {
      // The biggest *total* is the widest canvas, not the deepest picture: 6 h
      // over nine panels is 40 min a pixel, against 4 h over four panels' 1 h.
      const t = integrationTrend([
        mosaicRun(HOUR, 0.060, 4),          // shallowest: 15 min a pixel
        mosaicRun(6 * HOUR, 0.045, 9),      // biggest total, 40 min a pixel
        mosaicRun(4 * HOUR, 0.030, 4),      // deepest picture: 1 h a pixel
      ]);
      // shallow 0.25 h -> deep 1 h a pixel is 4x the light for half the grain.
      expect(t?.exponent).toBeCloseTo(0.5, 2);
      expect(t?.level).toBe("improving");
      expect(t?.hoursNow).toBeCloseTo(4.0, 3);
    });
  });
});
