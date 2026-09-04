import { describe, expect, it } from "vitest";
import type { RejectionOutlook } from "../../api/client";
import { rejectionOutlookNote } from "./rejectionOutlookNote";

function outlook(over: Partial<RejectionOutlook> = {}): RejectionOutlook {
  return {
    method: "sigma-clip",
    n_frames: 6,
    panel_depth: null,
    lone_outlier_min_frames: 11,
    reaches: false,
    user_chose: true,
    ...over,
  };
}

describe("rejectionOutlookNote", () => {
  it("warns when the user's saved sigma clip cannot reach the trails they have", () => {
    const note = rejectionOutlookNote(outlook(), 2);
    expect(note?.title).toMatch(/won't take these trails out/);
    expect(note?.text).toContain("2 subs here carry");
    expect(note?.text).toContain("sigma clipping");
    expect(note?.text).toContain("11");
    // The fix is named as the thing that works at every depth, never a method.
    expect(note?.text).toContain("Auto outlier removal");
  });

  it("says a mosaic's per-spot depth, not its frame count", () => {
    const note = rejectionOutlookNote(
      outlook({ n_frames: 20, panel_depth: 5 }), 3);
    expect(note?.text).toMatch(/about 5 land on any one spot of this mosaic/);
    // The 20 would be the reassuring number and it is the wrong one.
    expect(note?.text).not.toContain("there are 20");
  });

  it("says the singular for one streaked sub", () => {
    expect(rejectionOutlookNote(outlook(), 1)?.text).toContain("1 sub here carries");
  });

  it("has a different sentence when no rejection pass runs at all", () => {
    const note = rejectionOutlookNote(
      outlook({ method: "mean", n_frames: 3, lone_outlier_min_frames: null }), 1);
    expect(note?.title).toMatch(/Nothing will remove these trails/);
    expect(note?.text).toContain("plain average");
    expect(note?.text).toContain("from 3 subs up");
  });

  it("is silent when nothing carries a trail", () => {
    expect(rejectionOutlookNote(outlook(), 0)).toBeNull();
  });

  it("is silent when the rejection does reach", () => {
    expect(rejectionOutlookNote(outlook({ reaches: true }), 4)).toBeNull();
  });

  it("is silent when the app picked the method, not the user", () => {
    // The chain's own auto pick is the app doing its job; there is nothing to
    // tell anyone, even in the (impossible-by-construction) blind case.
    expect(rejectionOutlookNote(outlook({ user_chose: false }), 4)).toBeNull();
  });

  it("is silent with no verdict — nothing solved yet, or an older backend", () => {
    expect(rejectionOutlookNote(outlook({ reaches: null }), 4)).toBeNull();
    expect(rejectionOutlookNote(null, 4)).toBeNull();
    expect(rejectionOutlookNote(undefined, 4)).toBeNull();
  });

  it("speaks for a drizzled run too — the same clip, so the same blind spot", () => {
    // This replaces "is silent on a drizzled run": the old silence rested on the
    // memory budget settling the pass at run time, which only ever makes the
    // trail *more* likely to survive. The owner drizzles mosaics, whose panels
    // are exactly the thin stacks this note exists for.
    const note = rejectionOutlookNote(
      outlook({ method: "drizzle", n_frames: 40, panel_depth: 10 }), 4);
    expect(note?.title).toMatch(/won't take these trails out/);
    expect(note?.text).toContain("drizzle's own outlier removal");
    expect(note?.text).toMatch(/about 10 land on any one spot of this mosaic/);
    expect(note?.text).toContain("11");
  });

  it("does not offer the app's own choice as the drizzle fix", () => {
    // `auto_reject` is overridden while drizzle is on, so
    // `auto_reject_on_unattended` would change nothing — name the two things
    // that do work instead, and withhold the button.
    const note = rejectionOutlookNote(outlook({ method: "drizzle" }), 4);
    expect(note?.unattendedChoiceHelps).toBe(false);
    expect(note?.text).toContain("More subs");
    expect(note?.text).toContain("without drizzle");
    // …while the two branches it *does* fix still offer it.
    expect(rejectionOutlookNote(outlook(), 4)?.unattendedChoiceHelps).toBe(true);
    expect(rejectionOutlookNote(outlook({ method: "mean" }), 4)
      ?.unattendedChoiceHelps).toBe(true);
  });

  it("stays silent on a drizzled run that can reach", () => {
    expect(rejectionOutlookNote(
      outlook({ method: "drizzle", reaches: true }), 4)).toBeNull();
  });
});
