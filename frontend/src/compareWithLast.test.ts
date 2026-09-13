import { describe, expect, it } from "vitest";
import {
  pickCompareWithLast, pickFirstVsNow, sameTargetCompareHref,
} from "./compareWithLast";
import type { StackRun } from "./api/client";

function run(id: number, over: Partial<StackRun> = {}): StackRun {
  return {
    id,
    timestamp_utc: "2026-05-02T00:00:00Z",
    n_frames_used: 100,
    canvas_w: 1000,
    canvas_h: 800,
    has_preview: true,
    has_fits: true,
    has_tiff: false,
    ...over,
  } as StackRun;
}

describe("sameTargetCompareHref", () => {
  it("builds the bookmarkable A/B URL both surfaces use", () => {
    expect(sameTargetCompareHref("M_42", 7, 3)).toBe("/compare?a=M_42:7&b=M_42:3");
  });
});

describe("pickCompareWithLast", () => {
  it("pairs the newest picture with the one before it", () => {
    // `listStackRuns` is newest-first, so this is the order the page has.
    const pair = pickCompareWithLast([run(9), run(7), run(3)]);
    expect(pair?.newest.id).toBe(9);
    expect(pair?.previous.id).toBe(7);
  });

  it("says nothing on a target that has only been stacked once", () => {
    expect(pickCompareWithLast([run(9)])).toBeNull();
    expect(pickCompareWithLast([])).toBeNull();
    expect(pickCompareWithLast(undefined)).toBeNull();
    expect(pickCompareWithLast(null)).toBeNull();
  });

  it("skips a run with no picture — there would be nothing to put beside anything", () => {
    expect(pickCompareWithLast([run(9), run(7, { has_preview: false })])).toBeNull();
    const pair = pickCompareWithLast(
      [run(9), run(7, { has_preview: false }), run(3)]);
    expect(pair?.newest.id).toBe(9);
    expect(pair?.previous.id).toBe(3);
  });

  it("skips an editor export — that answers 'did my edit change anything?', not 'did another night help?'", () => {
    expect(pickCompareWithLast([run(9, { reusable: false }), run(7)])).toBeNull();
    const pair = pickCompareWithLast(
      [run(9, { reusable: false }), run(7, { reusable: true }), run(3, { reusable: true })]);
    expect(pair?.newest.id).toBe(7);
    expect(pair?.previous.id).toBe(3);
  });

  it("treats a run that never reported `reusable` as a genuine stack (older backend)", () => {
    const pair = pickCompareWithLast([run(9), run(7)]);
    expect(pair?.newest.id).toBe(9);
    expect(pair?.previous.id).toBe(7);
  });
});

describe("pickFirstVsNow", () => {
  it("pairs the newest picture with the FIRST one, not the one before it", () => {
    // `listStackRuns` is `ORDER BY timestamp_utc DESC`, so the last survivor is
    // the earliest stack — the picture at the bottom of History that a beginner
    // never scrolls to, and the whole point of this pairing.
    const pair = pickFirstVsNow([run(9), run(7), run(5), run(3)]);
    expect(pair?.newest.id).toBe(9);
    expect(pair?.first.id).toBe(3);
  });

  it("applies the same two honesty filters as `pickCompareWithLast`", () => {
    // A preview-less run at the bottom is not "your first picture" — there is no
    // picture — and neither is an editor export of a later stack.
    const noPicture = pickFirstVsNow(
      [run(9), run(7), run(3, { has_preview: false })]);
    expect(noPicture?.first.id).toBe(7);
    const export_ = pickFirstVsNow(
      [run(9), run(7), run(3, { reusable: false })]);
    expect(export_?.first.id).toBe(7);
  });

  it("says nothing when there is nothing to show", () => {
    expect(pickFirstVsNow([run(9)])).toBeNull();
    expect(pickFirstVsNow([])).toBeNull();
    expect(pickFirstVsNow(undefined)).toBeNull();
    expect(pickFirstVsNow(null)).toBeNull();
    // Only one *comparable* run, however many rows there are.
    expect(pickFirstVsNow([run(9), run(7, { has_preview: false })])).toBeNull();
  });

  it("is the same pair as `pickCompareWithLast` when there are exactly two", () => {
    // Not a defect — it is what lets the card offer one button instead of two
    // pointing at one URL. Pinned so the equality is a decision, not a surprise.
    const runs = [run(9), run(7)];
    expect(pickFirstVsNow(runs)?.first.id).toBe(pickCompareWithLast(runs)?.previous.id);
  });
});
