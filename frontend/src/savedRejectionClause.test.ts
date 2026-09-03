import { describe, expect, it } from "vitest";
import type { RejectionOutlook } from "./api/client";
import { savedRejectionClause } from "./savedRejectionClause";

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

describe("savedRejectionClause", () => {
  it("warns that the saved sigma clip cannot reach a lone trail", () => {
    const clause = savedRejectionClause(outlook());
    expect(clause).toContain("sigma clipping");
    expect(clause).toContain("6 subs");
    expect(clause).toContain("11");
    // The fix is named as the thing that works at every depth, never a method.
    expect(clause).toContain("Auto outlier removal");
  });

  it("is about the unattended path, not the stack in front of you", () => {
    // The Stack form's own `rejectionReachNudge` already speaks for the run the
    // user is about to trigger; this clause earns its place only by saying what
    // the *saved* default does on every night after this one.
    expect(savedRejectionClause(outlook())).toMatch(/overnight and one-click stacks/);
  });

  it("says a mosaic's per-spot depth, not its frame count", () => {
    const clause = savedRejectionClause(outlook({ n_frames: 20, panel_depth: 5 }));
    expect(clause).toMatch(/only about 5 subs land on any one spot of this mosaic/);
    // The 20 would be the reassuring number and it is the wrong one.
    expect(clause).not.toContain("20");
  });

  it("says the singular at a depth of one", () => {
    const clause = savedRejectionClause(outlook({ n_frames: 20, panel_depth: 1 }));
    expect(clause).toContain("only about 1 sub land");
  });

  it("has a different sentence when no rejection pass runs at all", () => {
    const clause = savedRejectionClause(
      outlook({ method: "mean", n_frames: 3, lone_outlier_min_frames: null }));
    expect(clause).toContain("plain average");
    expect(clause).toContain("from 3 subs up");
    expect(clause).not.toContain("sigma clipping");
  });

  it("is silent when the saved rejection does reach", () => {
    expect(savedRejectionClause(outlook({ reaches: true }))).toBeNull();
  });

  it("is silent when the app picked the method, not the user", () => {
    // Saving with Auto on leaves the choice to the chain, which picks a method
    // that works — that is the app doing its job, and saying so would be noise.
    expect(savedRejectionClause(outlook({ user_chose: false }))).toBeNull();
  });

  it("is silent with no verdict — nothing solved yet, or an older backend", () => {
    expect(savedRejectionClause(outlook({ reaches: null }))).toBeNull();
    expect(savedRejectionClause(null)).toBeNull();
    expect(savedRejectionClause(undefined)).toBeNull();
  });

  it("is silent on a drizzled run, whose rejection is settled at run time", () => {
    expect(savedRejectionClause(outlook({ method: "drizzle" }))).toBeNull();
  });

  it("is silent when there is no depth to talk about", () => {
    expect(savedRejectionClause(outlook({ n_frames: 0, panel_depth: null }))).toBeNull();
    expect(savedRejectionClause(outlook({ n_frames: undefined, panel_depth: null })))
      .toBeNull();
  });
});
