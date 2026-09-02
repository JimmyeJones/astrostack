import { describe, expect, it } from "vitest";
import type { StackRun } from "./api/client";
import { representativeRun } from "./representative";

function mkRun(overrides: Partial<StackRun> = {}): StackRun {
  return {
    id: 1, timestamp_utc: "2026-01-01T00:00:00", output_basename: "master",
    n_frames_used: 3, canvas_w: 480, canvas_h: 320,
    coverage_min: 3, coverage_max: 3, has_fits: true, has_tiff: false,
    has_preview: true, notes: null, ...overrides,
  };
}

// Newest first, the order `listStackRuns` returns.
const runs = [mkRun({ id: 4 }), mkRun({ id: 3 }), mkRun({ id: 2 })];

describe("representativeRun", () => {
  it("takes the newest picture when nothing is pinned", () => {
    const { run, pinned, newer } = representativeRun(runs, null);
    expect(run?.id).toBe(4);
    expect(pinned).toBe(false);
    expect(newer).toBeUndefined();
  });

  it("takes the pinned cover over a newer stack — the A5 regression", () => {
    // Pin run 3, re-stack to run 4: the Library tile, the Best wall and the
    // montage all show run 3, and the Target page used to show run 4.
    const { run, pinned, newer } = representativeRun(runs, 3);
    expect(run?.id).toBe(3);
    expect(pinned).toBe(true);
    expect(newer?.id).toBe(4);
  });

  it("reports no newer picture when the cover already is the newest", () => {
    const { run, pinned, newer } = representativeRun(runs, 4);
    expect(run?.id).toBe(4);
    expect(pinned).toBe(true);
    expect(newer).toBeUndefined();
  });

  it("degrades to the newest picture when the pinned cover has no preview", () => {
    // Same silent fallback as the backend's `_representative_run`: a cover whose
    // preview file has gone must not blank the page.
    const list = [mkRun({ id: 4 }), mkRun({ id: 3, has_preview: false })];
    const { run, pinned } = representativeRun(list, 3);
    expect(run?.id).toBe(4);
    expect(pinned).toBe(false);
  });

  it("degrades to the newest picture when the pinned cover is gone entirely", () => {
    const { run, pinned } = representativeRun(runs, 99);
    expect(run?.id).toBe(4);
    expect(pinned).toBe(false);
  });

  it("skips a newest run that has no preview yet", () => {
    const list = [mkRun({ id: 5, has_preview: false }), mkRun({ id: 4 })];
    expect(representativeRun(list, null).run?.id).toBe(4);
  });

  it("still yields the newest run when nothing has a preview at all", () => {
    // The action row (Edit, Stack) works on a run that has yet to render one.
    const list = [mkRun({ id: 5, has_preview: false })];
    expect(representativeRun(list, null).run?.id).toBe(5);
  });

  it("is empty on a target with no stacks", () => {
    expect(representativeRun([], 3).run).toBeUndefined();
    expect(representativeRun(undefined, 3).run).toBeUndefined();
  });
});
