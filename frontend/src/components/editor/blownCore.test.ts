import { describe, expect, it } from "vitest";
import {
  blownCoreButtonLabel, blownCoreCaption, blownCoreStretchOp,
} from "./blownCore";

describe("blownCoreCaption", () => {
  it("names the problem and promises only what the fix actually does", () => {
    const text = blownCoreCaption({ strength: 0.4, flat_fraction: 0.62 })!;
    expect(text).toContain("flat white");
    expect(text).toContain("still in your data");
    // The shoulder moves only tones above the knee, so the sky is untouched —
    // the copy must not imply a brightness change.
    expect(text).toContain("leaves the sky exactly where it is");
  });

  it("says nothing when the server declined to suggest a strength", () => {
    // No core, a star-sized one, one barely clipped, one saturated at capture, or
    // one the knob can't reopen — the server has already made that call.
    expect(blownCoreCaption({ strength: null })).toBeNull();
    expect(blownCoreCaption({ strength: null, flat_fraction: 0.9 })).toBeNull();
    expect(blownCoreCaption(undefined)).toBeNull();
  });

  it("ignores a nonsensical strength rather than offering a no-op button", () => {
    expect(blownCoreCaption({ strength: 0 })).toBeNull();
    expect(blownCoreCaption({ strength: NaN })).toBeNull();
  });

  it("stops nagging once the slider is at or past the suggested strength", () => {
    const sug = { strength: 0.4, flat_fraction: 0.62 };
    expect(blownCoreCaption(sug, 0)).not.toBeNull();
    expect(blownCoreCaption(sug, 0.35)).not.toBeNull();
    expect(blownCoreCaption(sug, 0.4)).toBeNull();
    expect(blownCoreCaption(sug, 0.8)).toBeNull();
  });

  it("treats a missing or unusable slider value as no protection yet", () => {
    const sug = { strength: 0.4 };
    expect(blownCoreCaption(sug, undefined)).not.toBeNull();
    expect(blownCoreCaption(sug, null)).not.toBeNull();
    expect(blownCoreCaption(sug, "0.9")).not.toBeNull();
    expect(blownCoreCaption(sug, NaN)).not.toBeNull();
  });
});

describe("blownCoreButtonLabel", () => {
  it("shows the strength it will apply", () => {
    expect(blownCoreButtonLabel({ strength: 0.6 }))
      .toBe("Hold back highlights (0.6)");
  });
});

describe("blownCoreStretchOp", () => {
  const stretch = { uid: "s1", id: "tone.stretch", enabled: true };
  const curves = { uid: "c1", id: "tone.curves", enabled: true };

  it("picks the recipe's first Stretch, like the server's own fallback", () => {
    // `solve_highlight_protect` with no uid solves for the *first* tone.stretch,
    // so the nudge on the Auto note must name the same op — otherwise the note
    // and the op panel could offer two answers about one picture.
    const second = { uid: "s2", id: "tone.stretch", enabled: true };
    expect(blownCoreStretchOp([curves, stretch, second])).toBe(stretch);
  });

  it("says nothing when the recipe has no Stretch at all", () => {
    expect(blownCoreStretchOp([curves])).toBeNull();
    expect(blownCoreStretchOp([])).toBeNull();
    expect(blownCoreStretchOp(undefined)).toBeNull();
  });

  it("says nothing when the Stretch is switched off", () => {
    // A bypassed op is not rendering, so there is nothing to offer to change.
    expect(blownCoreStretchOp([{ ...stretch, enabled: false }])).toBeNull();
  });

  it("treats an op with no `enabled` field as on", () => {
    expect(blownCoreStretchOp([{ uid: "s1", id: "tone.stretch" }])).not.toBeNull();
  });
});
