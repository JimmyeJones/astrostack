import { describe, expect, it } from "vitest";
import {
  UNSTRETCHED_GALLERY_HINT, UNSTRETCHED_HINT, UNSTRETCHED_LABEL,
  showsUnstretchedChip,
} from "./unstretched";

describe("showsUnstretchedChip", () => {
  it("renders only on an explicit false", () => {
    expect(showsUnstretchedChip(false)).toBe(true);
    expect(showsUnstretchedChip(true)).toBe(false);
    // "The backend didn't say" is not "linear": an older build sends neither,
    // and a chip that appeared because a field was missing would accuse every
    // picture in the library.
    expect(showsUnstretchedChip(undefined)).toBe(false);
    expect(showsUnstretchedChip(null)).toBe(false);
  });
});

describe("the two walls' copy", () => {
  it("shares one label so they cannot drift", () => {
    expect(UNSTRETCHED_LABEL).toBe("Not stretched yet");
  });

  it("both explain what a linear stack is, in the same words", () => {
    for (const hint of [UNSTRETCHED_HINT, UNSTRETCHED_GALLERY_HINT]) {
      expect(hint).toContain("straight out of the stacker");
      expect(hint).toContain("darkest part of the range");
      // Never a dead end: both say it is undoable, because the whole objection
      // to an app touching your picture is not being able to get it back.
      expect(hint).toContain("reversible");
    }
  });

  it("differ only in the way in each card can actually offer", () => {
    // The Library card is one <Link> to the target, so an anchor in its chip
    // would be invalid HTML and the run's editor is a screen further in.
    expect(UNSTRETCHED_HINT).toContain("Open it and press Auto");
    expect(UNSTRETCHED_HINT).not.toContain("Edit image");
    // A Gallery card already carries an "Edit image" button straight to that
    // run's editor, which since v0.390.0 opens on Auto — so name it.
    expect(UNSTRETCHED_GALLERY_HINT).toContain("Edit image");
    expect(UNSTRETCHED_GALLERY_HINT).toContain("starts you off with Auto");
  });
});
