import { describe, expect, it } from "vitest";

import {
  FRAME_WINDOW_STEP, frameWindowForIndex, frameWindowNote, growFrameWindow,
} from "./frameWindow";

describe("growFrameWindow", () => {
  it("adds one step", () => {
    expect(growFrameWindow(300, 5477, 300)).toBe(600);
  });

  it("never grows past the list", () => {
    expect(growFrameWindow(300, 312, 300)).toBe(312);
    expect(growFrameWindow(5477, 5477, 300)).toBe(5477);
  });

  it("uses the shared step by default, so the table and its foot agree", () => {
    expect(growFrameWindow(0, 100000)).toBe(FRAME_WINDOW_STEP);
  });
});

describe("frameWindowForIndex", () => {
  it("leaves a window that already covers the index alone", () => {
    expect(frameWindowForIndex(300, 12, 300)).toBe(300);
    // The last row of the window is inside it — off-by-one in the direction
    // that would render one row short of the selection.
    expect(frameWindowForIndex(300, 299, 300)).toBe(300);
  });

  it("grows in whole steps to cover a selection past the end", () => {
    expect(frameWindowForIndex(300, 300, 300)).toBe(600);
    expect(frameWindowForIndex(300, 901, 300)).toBe(1200);
  });

  it("never shrinks a window", () => {
    expect(frameWindowForIndex(900, 5, 300)).toBe(900);
  });
});

describe("frameWindowNote", () => {
  it("says nothing when every sub is rendered", () => {
    // The ordinary case: almost every target is smaller than one window, and a
    // row reading "showing all 12 of 12" is clutter on a page already called busy.
    expect(frameWindowNote(12, 12)).toBeNull();
    expect(frameWindowNote(300, 300)).toBeNull();
    expect(frameWindowNote(0, 0)).toBeNull();
  });

  it("names both numbers, grouped, and says *first*", () => {
    expect(frameWindowNote(300, 5477)).toBe("Showing the first 300 of 5,477 subs.");
  });
});
