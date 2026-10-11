import { describe, expect, it } from "vitest";
import type { NightSummary } from "../api/client";
import {
  PACE_LOOKBACK_NIGHTS,
  clearNightsFromPace,
  estimateClearNights,
  nightWord,
} from "./clearNights";

/** One night's summary, newest-first order supplied by the caller. Only the
 *  fields the estimate reads are interesting; the rest carry sane filler.
 *
 *  `nKept` defaults to `nFrames` — a night that kept everything it caught,
 *  which is what an ordinary short mosaic night looks like. It is a parameter
 *  because the helper used to tie `n_kept` to `n_frames` *and* `exposure_s` to
 *  `kept_exposure_s`, so no fixture here could tell "threw its subs away" from
 *  "was simply short" — which is exactly the distinction the all-duds branch
 *  turned out to be missing. */
function night(keptExposureS: number, nFrames = 60, nKept = nFrames): NightSummary {
  return {
    start_utc: "2026-01-01T21:00:00Z",
    end_utc: "2026-01-02T02:00:00Z",
    n_frames: nFrames,
    n_kept: nKept,
    n_set_aside: nFrames - nKept,
    // What the night recorded is independent of what it kept: a dud night
    // records a full session's worth and keeps a sliver of it.
    exposure_s: nFrames > 0 ? (keptExposureS * nFrames) / Math.max(nKept, 1) : 0,
    kept_exposure_s: keptExposureS,
    median_fwhm_px: 3.2,
    verdict: "sharp",
    is_best: false,
    reject_buckets: {},
  };
}

const HOUR = 3600;

describe("estimateClearNights", () => {
  it("divides the goal gap by the median kept integration per night", () => {
    // Two 1 h nights → pace 1 h; a 2 h gap is two more clear nights.
    const e = estimateClearNights(2 * HOUR, [night(HOUR), night(HOUR)]);
    expect(e?.nights).toBe(2);
    expect(e?.paceSeconds).toBe(HOUR);
    expect(e?.nightsUsed).toBe(2);
    expect(e?.text).toContain("about 2 more clear nights");
    expect(e?.text).toContain("1.0 h of kept subs per clear night");
  });

  it("says 'night' (singular) when one more night does it", () => {
    const e = estimateClearNights(0.5 * HOUR, [night(HOUR), night(HOUR)]);
    expect(e?.nights).toBe(1);
    expect(e?.text).toContain("about 1 more clear night.");
  });

  it("rounds a part-night up — you can't shoot 1.2 nights", () => {
    const e = estimateClearNights(2.2 * HOUR, [night(HOUR), night(HOUR)]);
    expect(e?.nights).toBe(3);
  });

  it("uses the median so one short night doesn't skew the pace", () => {
    // 10 min / 1 h / 1 h → median 1 h, not the 43 min mean.
    const e = estimateClearNights(3 * HOUR, [night(600), night(HOUR), night(HOUR)]);
    expect(e?.paceSeconds).toBe(HOUR);
    expect(e?.nights).toBe(3);
  });

  it(`only looks back ${PACE_LOOKBACK_NIGHTS} nights, so an old habit doesn't linger`, () => {
    // Five recent 30 min nights, then a run of ancient 4 h ones. The pace must
    // reflect what the owner is getting *now* (30 min), not the old marathons.
    const recent = Array.from({ length: PACE_LOOKBACK_NIGHTS }, () => night(1800));
    const ancient = Array.from({ length: 6 }, () => night(4 * HOUR));
    const e = estimateClearNights(3 * HOUR, [...recent, ...ancient]);
    expect(e?.paceSeconds).toBe(1800);
    expect(e?.nights).toBe(6);
  });

  it("says nothing once the goal is met", () => {
    expect(estimateClearNights(0, [night(HOUR), night(HOUR)])).toBeNull();
    expect(estimateClearNights(-HOUR, [night(HOUR), night(HOUR)])).toBeNull();
  });

  it("says nothing from a single night — one session is not a pace", () => {
    expect(estimateClearNights(2 * HOUR, [night(HOUR)])).toBeNull();
  });

  it("says nothing with no night history at all", () => {
    expect(estimateClearNights(2 * HOUR, [])).toBeNull();
    expect(estimateClearNights(2 * HOUR, null)).toBeNull();
    expect(estimateClearNights(2 * HOUR, undefined)).toBeNull();
  });

  it("ignores a night that recorded no frames", () => {
    // A single real night plus an empty one is still only one night of accrual.
    expect(estimateClearNights(2 * HOUR, [night(HOUR), night(0, 0)])).toBeNull();
  });

  it("says nothing when only one recent night actually accrued anything", () => {
    // One good night among duds is data, not a pace — projecting the whole
    // remaining goal off it would be a confident guess from nothing.
    const e = estimateClearNights(2 * HOUR, [night(HOUR), night(0), night(0)]);
    expect(e).toBeNull();
  });

  it("advises checking focus when recent nights kept essentially nothing", () => {
    // Three real sessions of 60 subs each that kept 1, 1 and 2 of them — the
    // case this branch exists for, and now stated as such: what makes it a dud
    // is the *discarding*, not the short kept total.
    const e = estimateClearNights(
      2 * HOUR, [night(0, 60, 1), night(0, 60, 1), night(30, 60, 2)]);
    expect(e).not.toBeNull();
    expect(e?.nights).toBeNull();          // no ETA — nothing honest to divide by
    expect(e?.paceSeconds).toBe(0);
    expect(e?.nightsUsed).toBe(3);
    expect(e?.text).toContain("kept almost nothing");
    expect(e?.text).toContain("checking focus");
  });

  it("does not call a SHORT night a dud, or send the owner to check focus",
    () => {
      // The owner's own shape, and the reason this branch needed splitting: a
      // 2x2 mosaic revisited across eleven nights takes 6 subs a visit and
      // keeps all 6 — `n_kept` 6 of 6, `n_set_aside` 0, every night graded
      // `sharp` — which is 60 s of kept exposure against a 120 s pace floor.
      // Nothing was discarded and nothing is wrong, so there is no pace to
      // quote and nothing to report: the card self-hides rather than claiming
      // the nights "kept almost nothing" and prescribing a focus check, which
      // it did on the app's own `--dithered` sample.
      const mosaicNights = Array.from({ length: 5 }, () => night(60, 6));
      expect(estimateClearNights(11 * HOUR, mosaicNights)).toBeNull();
    });

  it("still says nothing when a night's exposure is unreadable", () => {
    // `exposure_s` is a sum of EXPTIME headers and can be 0 on subs that carry
    // none. A share of zero is not a judgement about anybody's focus, so the
    // dud test refuses rather than firing on the division.
    const blank = [night(0, 60, 60), night(0, 60, 60)];
    expect(estimateClearNights(2 * HOUR, blank)).toBeNull();
  });

  it("never divides by zero or returns a non-finite estimate", () => {
    // Two nights with no kept exposure at all: whichever way the branch below
    // goes, no number comes out. They kept every sub they caught, so the answer
    // is silence; a pair that really did discard its subs gets `nights: null`
    // (the all-duds test above). Neither can divide.
    expect(estimateClearNights(2 * HOUR, [night(0), night(0)])).toBeNull();
    const dud = estimateClearNights(2 * HOUR, [night(0, 60, 1), night(0, 60, 1)]);
    expect(dud?.nights).toBeNull();
    // …and a nonsense gap is refused outright rather than propagated.
    expect(estimateClearNights(Number.NaN, [night(HOUR), night(HOUR)])).toBeNull();
    expect(estimateClearNights(Number.POSITIVE_INFINITY, [night(HOUR), night(HOUR)]))
      .toBeNull();
  });

  it("gives a big but honest number when the goal is far off at a slow pace", () => {
    // 20 h to go at 30 min a night. Discouraging, but true — and better than a
    // silently capped figure the owner would plan around.
    const e = estimateClearNights(20 * HOUR, [night(1800), night(1800), night(1800)]);
    expect(e?.nights).toBe(40);
  });
});

describe("clearNightsFromPace", () => {
  it("gives the same answer and wording as the night-list estimate", () => {
    // The Library overview gets its pace from the server; the Target page
    // derives it from the night list. Same target, same sentence — otherwise the
    // two screens would quote different ETAs for the same picture.
    const fromNights = estimateClearNights(2 * HOUR, [night(HOUR), night(HOUR)]);
    const fromPace = clearNightsFromPace(2 * HOUR, HOUR);
    expect(fromPace?.nights).toBe(fromNights?.nights);
    expect(fromPace?.text).toBe(fromNights?.text);
  });

  it("rounds up and never promises less than one more night", () => {
    expect(clearNightsFromPace(2.1 * HOUR, HOUR)?.nights).toBe(3);
    expect(clearNightsFromPace(60, 10 * HOUR)?.nights).toBe(1);
  });

  it("says nothing without a gap or a usable pace", () => {
    expect(clearNightsFromPace(0, HOUR)).toBeNull();
    expect(clearNightsFromPace(-HOUR, HOUR)).toBeNull();
    expect(clearNightsFromPace(NaN, HOUR)).toBeNull();
    expect(clearNightsFromPace(HOUR, null)).toBeNull();
    expect(clearNightsFromPace(HOUR, undefined)).toBeNull();
    expect(clearNightsFromPace(HOUR, 0)).toBeNull();
    expect(clearNightsFromPace(HOUR, -HOUR)).toBeNull();
    expect(clearNightsFromPace(HOUR, Infinity)).toBeNull();
  });

  it("reports the honest big number rather than a flattering cap", () => {
    // 40 h to go at 30 min a night really is 80 clear nights; the *card* decides
    // whether that's worth showing, this helper never softens it.
    expect(clearNightsFromPace(40 * HOUR, 0.5 * HOUR)?.nights).toBe(80);
  });
});

describe("nightWord", () => {
  it("is singular only for one", () => {
    expect(nightWord(1)).toBe("night");
    expect(nightWord(2)).toBe("nights");
    expect(nightWord(0)).toBe("nights");
  });
});
