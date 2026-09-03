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

  it("is silent on a drizzled run, whose rejection is settled at run time", () => {
    expect(rejectionOutlookNote(outlook({ method: "drizzle" }), 4)).toBeNull();
  });
});
