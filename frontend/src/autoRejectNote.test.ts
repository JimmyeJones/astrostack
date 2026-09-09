import { describe, expect, it } from "vitest";
import { autoRejectMethodNote } from "./autoRejectNote";

describe("autoRejectMethodNote", () => {
  it("names the method and the boundary on a single field", () => {
    const note = autoRejectMethodNote(
      { method: "min_max", switch_at_frames: 11, n_frames: 6, panel_depth: null });
    expect(note).toContain("with 6 accepted, solved subs it will use min/max rejection");
    expect(note).toContain("switches to sigma clipping from about 11 subs");
  });

  it("says sigma clipping once the count is past the boundary", () => {
    const note = autoRejectMethodNote(
      { method: "sigma_clip", switch_at_frames: 11, n_frames: 40, panel_depth: null });
    expect(note).toContain("with 40 accepted, solved subs it will use sigma clipping");
    expect(note).toContain("Below about 11 subs");
  });

  it("speaks in panel depth on a mosaic, because that is what decided", () => {
    // The bug this exists for: 21 subs is past the 11-frame boundary, but they
    // are four panels only 3 deep, so the engine runs min/max. A note quoting
    // 21 subs and naming min/max reads as a bug; this one gives the reason.
    const note = autoRejectMethodNote(
      { method: "min_max", switch_at_frames: 11, n_frames: 21, panel_depth: 3 });
    expect(note).toContain("how many subs land on each pixel");
    expect(note).toContain("your 21 subs are spread across a mosaic that is only 3 deep");
    expect(note).toContain("min/max rejection");
    expect(note).toContain("about 11 subs overlap on one spot");
    // …and it must not claim the frame count is what chose the method.
    expect(note).not.toContain("picks the method from your frame count");
  });

  it("says so in depth terms when a deep mosaic does reach sigma clipping", () => {
    const note = autoRejectMethodNote(
      { method: "sigma_clip", switch_at_frames: 11, n_frames: 200, panel_depth: 30 });
    expect(note).toContain("only 30 deep where it is thinnest");
    expect(note).toContain("enough for sigma clipping");
  });

  it("keeps the frame wording when the depth says nothing new", () => {
    // A single field (null), an older backend (absent), and a mosaic whose
    // panels all overlap fully (depth === n) are all the same case: quoting the
    // same number twice would be noise, not honesty.
    for (const depth of [null, undefined, 6]) {
      const note = autoRejectMethodNote(
        { method: "min_max", switch_at_frames: 11, n_frames: 6, panel_depth: depth });
      expect(note).toContain("picks the method from your frame count");
    }
  });

  it("says nothing when Auto is not deciding, or nothing has solved", () => {
    expect(autoRejectMethodNote(null)).toBeNull();
    expect(autoRejectMethodNote(undefined)).toBeNull();
    expect(autoRejectMethodNote(
      { method: "min_max", switch_at_frames: 11, n_frames: 0 })).toBeNull();
  });
});
