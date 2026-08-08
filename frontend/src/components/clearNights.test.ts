import { describe, expect, it } from "vitest";
import type { NightSummary } from "../api/client";
import { PACE_LOOKBACK_NIGHTS, estimateClearNights } from "./clearNights";

/** One night's summary, newest-first order supplied by the caller. Only the two
 *  fields the estimate reads are interesting; the rest carry sane filler. */
function night(keptExposureS: number, nFrames = 60): NightSummary {
  return {
    start_utc: "2026-01-01T21:00:00Z",
    end_utc: "2026-01-02T02:00:00Z",
    n_frames: nFrames,
    n_kept: nFrames,
    n_set_aside: 0,
    exposure_s: keptExposureS,
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
    const e = estimateClearNights(2 * HOUR, [night(0), night(0), night(30)]);
    expect(e).not.toBeNull();
    expect(e?.nights).toBeNull();          // no ETA — nothing honest to divide by
    expect(e?.paceSeconds).toBe(0);
    expect(e?.nightsUsed).toBe(3);
    expect(e?.text).toContain("kept almost nothing");
    expect(e?.text).toContain("checking focus");
  });

  it("never divides by zero or returns a non-finite estimate", () => {
    const e = estimateClearNights(2 * HOUR, [night(0), night(0)]);
    expect(e?.nights).toBeNull();
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
