import { describe, expect, it } from "vitest";
import { pickCompareWithLast, sameTargetCompareHref } from "./compareWithLast";
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
