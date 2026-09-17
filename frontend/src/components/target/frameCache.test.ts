import { describe, expect, it } from "vitest";
import { replaceFrameInList } from "./frameCache";
import type { Frame } from "../../api/client";

function mkFrame(id: number, overrides: Partial<Frame> = {}): Frame {
  return {
    id, name: `f${id}.fits`, timestamp_utc: "2026-01-01T00:00:00",
    exposure_s: 30, gain: 100, width_px: 480, height_px: 320,
    bayer_pattern: "RGGB", solved: true, ra_center_deg: 10, dec_center_deg: 20,
    ra_hint_deg: null, dec_hint_deg: null, fwhm_px: 2.5, star_count: 100,
    sky_adu_median: 500, eccentricity_median: 0.4, transparency_score: 5000,
    streak_detected: false,
    accept: true, reject_reason: null, user_override: false, ...overrides,
  };
}

describe("replaceFrameInList", () => {
  it("swaps the matching row and leaves every other one identical", () => {
    const list = [mkFrame(1), mkFrame(2), mkFrame(3)];
    const graded = mkFrame(2, { accept: false, reject_reason: "user", user_override: true });
    const next = replaceFrameInList(list, graded);
    expect(next.map((f) => f.id)).toEqual([1, 2, 3]);
    expect(next[1]).toBe(graded);
    // Untouched rows are the *same objects*, so React memoisation downstream
    // sees exactly one row change.
    expect(next[0]).toBe(list[0]);
    expect(next[2]).toBe(list[2]);
  });

  it("does not mutate the list it was given", () => {
    const list = [mkFrame(1), mkFrame(2)];
    replaceFrameInList(list, mkFrame(2, { accept: false }));
    expect(list[1].accept).toBe(true);
  });

  it("returns the same array when the id is not in it", () => {
    // A cached list for another target, or one that has not loaded the row yet:
    // returning an equal copy would re-render it for nothing.
    const list = [mkFrame(1), mkFrame(2)];
    expect(replaceFrameInList(list, mkFrame(99))).toBe(list);
  });

  it("is a no-op on an empty list", () => {
    const list: Frame[] = [];
    expect(replaceFrameInList(list, mkFrame(1))).toBe(list);
  });
});
