import { describe, expect, it } from "vitest";
import { rejectionReachNudge } from "./rejectionReachNudge";
import type { StackEstimate } from "./api/client";

type Reach = NonNullable<StackEstimate["rejection_reach"]>;

const reach = (over: Partial<Reach>): Reach => ({
  method: "sigma-clip", n_frames: 6, lone_outlier_min_frames: 11, reaches: false,
  ...over,
});

// The form's own default state: sigma clipping ticked, nothing else.
const defaults = { sigma_clip: true };

describe("rejectionReachNudge", () => {
  it("warns when sigma clipping runs but is blind to a lone trail", () => {
    const nudge = rejectionReachNudge(reach({}), defaults);
    expect(nudge).not.toBeNull();
    expect(nudge!.text).toContain("6 subs");
    expect(nudge!.text).toContain("about 11 frames up");
    expect(nudge!.fix).toEqual({
      key: "auto_reject", label: "Turn on Auto outlier removal",
    });
  });

  it("never tells the user to turn their only rejection off", () => {
    // The bug this replaces: the old caution offered "Turn off sigma clipping"
    // on exactly these stacks, which swaps no rejection for no rejection.
    const nudge = rejectionReachNudge(reach({}), defaults);
    expect(nudge!.text.toLowerCase()).not.toContain("turn it off");
    expect(nudge!.fix!.key).toBe("auto_reject");
  });

  it("says a small stack will combine as a plain average", () => {
    const nudge = rejectionReachNudge(
      reach({ method: "mean", n_frames: 3, lone_outlier_min_frames: null }),
      defaults,
    );
    expect(nudge!.text).toContain("plain average");
    expect(nudge!.text).toContain("3 subs");
    expect(nudge!.fix).not.toBeNull();
  });

  it("offers no button below min/max's own three-frame floor", () => {
    const nudge = rejectionReachNudge(
      reach({ method: "mean", n_frames: 2, lone_outlier_min_frames: null }),
      defaults,
    );
    expect(nudge!.text).toContain("no outlier removal can run at all");
    expect(nudge!.fix).toBeNull();
  });

  it("is silent once the rejection actually reaches a lone outlier", () => {
    expect(rejectionReachNudge(
      reach({ n_frames: 40, reaches: true }), defaults)).toBeNull();
    expect(rejectionReachNudge(
      reach({ method: "min-max-reject", n_frames: 4, reaches: true }),
      { min_max_reject: true })).toBeNull();
  });

  it("is silent when the user asked for no rejection at all", () => {
    // A caution about protection you're not getting must not become a nag at
    // someone who deliberately opted out.
    expect(rejectionReachNudge(reach({ method: "mean" }), {})).toBeNull();
    expect(rejectionReachNudge(
      reach({ method: "mean" }), { sigma_clip: false })).toBeNull();
  });

  it("warns when drizzle's own rejection is on but blind at this depth", () => {
    // This replaces "leaves drizzle alone": drizzle's two-pass rejection is the
    // same κ·σ clip with the same κ, so it has the same blind band — and the
    // owner drizzles mosaics, whose panels sit inside it.
    const nudge = rejectionReachNudge(
      reach({ method: "drizzle", n_frames: 8 }),
      { drizzle: true, drizzle_reject: true },
    );
    expect(nudge!.text).toContain("Drizzle's outlier removal is on");
    expect(nudge!.text).toContain("8 subs");
    expect(nudge!.text).toContain("about 11 frames up");
    // No one-click fix: `auto_reject` is overridden while drizzle is on, so a
    // button here would change nothing.
    expect(nudge!.fix).toBeNull();
  });

  it("says nothing about drizzle rejection the user never asked for", () => {
    // Drizzle on, its rejection off: the sigma-clip tick below it is inert, so
    // "you're not getting the protection you asked for" would be untrue.
    expect(rejectionReachNudge(
      reach({ method: "drizzle", lone_outlier_min_frames: null }),
      { sigma_clip: true, drizzle: true })).toBeNull();
  });

  it("is silent once a drizzled stack is deep enough to clip", () => {
    expect(rejectionReachNudge(
      reach({ method: "drizzle", n_frames: 40, reaches: true }),
      { drizzle: true, drizzle_reject: true })).toBeNull();
  });

  it("says nothing when the backend is older or has no frames to size", () => {
    expect(rejectionReachNudge(undefined, defaults)).toBeNull();
    expect(rejectionReachNudge(null, defaults)).toBeNull();
    expect(rejectionReachNudge(
      reach({ method: "mean", n_frames: 0 }), defaults)).toBeNull();
  });

  it("quotes the engine's threshold rather than a hard-coded 11", () => {
    const loose = rejectionReachNudge(
      reach({ n_frames: 4, lone_outlier_min_frames: 6 }), defaults);
    expect(loose!.text).toContain("about 6 frames up");
  });

  it("uses singular wording for a one-sub stack", () => {
    const nudge = rejectionReachNudge(
      reach({ method: "mean", n_frames: 1, lone_outlier_min_frames: null }),
      defaults);
    expect(nudge!.text).toContain("1 sub,");
    expect(nudge!.text).not.toContain("1 subs");
  });
});
