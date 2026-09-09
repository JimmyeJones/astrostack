import { describe, expect, it } from "vitest";
import { autoStackNudge, type AutoStackNudgeInput } from "./autoStackNudge";

/** A night that *would* have been stacked: one target, plenty of kept subs, and
 *  nothing produced from it. Each test moves exactly one thing away from that. */
function night(over: Partial<AutoStackNudgeInput> = {}): AutoStackNudgeInput {
  return {
    autoStack: false,
    minFrames: 3,
    targetsKept: [42],
    nNewPictures: 0,
    ...over,
  };
}

describe("autoStackNudge", () => {
  it("offers the switch on a night the app captured and made nothing of", () => {
    const s = autoStackNudge(night());
    expect(s).toContain("Hands-off auto-stack is switched off");
    // The promise is about behaviour, never about a picture this night would
    // have produced — auto-stack counts *located* subs and this reads *kept*.
    expect(s).not.toMatch(/would have/i);
    // And it names the way back out, because an on-by-default surprise is the
    // thing the owner has been bitten by before.
    expect(s).toContain("Settings");
  });

  it("says nothing when auto-stack is already on", () => {
    expect(autoStackNudge(night({ autoStack: true }))).toBeNull();
  });

  it("says nothing while the setting is still loading", () => {
    // Not "assume off": a note that renders against an unresolved query flashes
    // on every Dashboard load and then withdraws itself.
    expect(autoStackNudge(night({ autoStack: undefined }))).toBeNull();
  });

  it("says nothing when the app did make a picture in the window", () => {
    // Something stacked — a manual run, or a scan under different settings. The
    // note would be contradicted by the lines directly above it.
    expect(autoStackNudge(night({ nNewPictures: 1 }))).toBeNull();
  });

  it("says nothing on a night too thin for the floor to have passed anyway", () => {
    expect(autoStackNudge(night({ targetsKept: [2], minFrames: 3 }))).toBeNull();
    expect(autoStackNudge(night({ targetsKept: [3], minFrames: 3 }))).not.toBeNull();
  });

  it("judges the floor per target, not on the night's total", () => {
    // Four targets of two subs each is eight subs and no picture: auto-stack's
    // floor is per target, so the offer must not fire on the sum.
    expect(autoStackNudge(night({ targetsKept: [2, 2, 2, 2], minFrames: 3 }))).toBeNull();
    expect(autoStackNudge(night({ targetsKept: [2, 2, 9], minFrames: 3 }))).not.toBeNull();
  });

  it("falls back to the shipped floor when the setting has not loaded", () => {
    expect(autoStackNudge(night({ minFrames: undefined, targetsKept: [2] }))).toBeNull();
    expect(autoStackNudge(night({ minFrames: undefined, targetsKept: [3] }))).not.toBeNull();
  });

  it("never lets a zero or negative floor turn one sub into an offer", () => {
    // A user may legitimately set the floor to 1; below that the value is junk
    // and must not make an empty night look stackable.
    expect(autoStackNudge(night({ minFrames: 0, targetsKept: [0] }))).toBeNull();
    expect(autoStackNudge(night({ minFrames: -5, targetsKept: [0] }))).toBeNull();
    expect(autoStackNudge(night({ minFrames: 1, targetsKept: [1] }))).not.toBeNull();
  });

  it("says nothing on a night with no targets at all", () => {
    expect(autoStackNudge(night({ targetsKept: [] }))).toBeNull();
  });
});
