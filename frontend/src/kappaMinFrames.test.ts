import { describe, it, expect } from "vitest";

import { kappaMinFrames } from "./kappaMinFrames";
import cases from "./kappaMinFrames.cases.json";

describe("kappaMinFrames", () => {
  it("agrees with the engine on every case in the shared table", () => {
    // The other half of `tests/test_kappa_min_frames_mirror.py`: the table is
    // generated from `seestack.stack.stacker.kappa_min_frames` and checked
    // against it there, and read here, so the two can only drift together.
    for (const [kappa, want] of cases.cases as [number, number][]) {
      expect(kappaMinFrames(kappa)).toBe(want);
    }
  });

  it("answers 11 at the app default κ=3 — the figure the app has been quoting", () => {
    expect(kappaMinFrames(3)).toBe(11);
  });

  it("never answers below the three-sample floor every method shares", () => {
    // A tiny κ would make the formula answer 1 or 2, which no accumulator can
    // act on: `MinMaxRejectAccumulator` falls through to a plain mean below 3.
    expect(kappaMinFrames(0.1)).toBe(3);
    expect(kappaMinFrames(1)).toBe(3);
  });

  it("declines rather than guessing when κ can't be read", () => {
    // A run whose stored options are absent, garbled or nonsensical gets no
    // figure at all — quoting the default's 11 for a stack clipped at some
    // other κ would be its own untruth, and every caller has a wording that
    // works without the number.
    for (const k of [null, undefined, NaN, Infinity, 0, -3]) {
      expect(kappaMinFrames(k as number)).toBeNull();
    }
  });
});
