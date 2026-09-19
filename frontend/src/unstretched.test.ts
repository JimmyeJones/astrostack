import { describe, expect, it } from "vitest";
import {
  UNSTRETCHED_GALLERY_HINT, UNSTRETCHED_HINT, UNSTRETCHED_LABEL,
  showsUnstretchedChip, unstretchedEditPath, unstretchedIsLinkable,
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

  it("differ only in the control each card can actually offer", () => {
    // Both now promise one click; they point at different controls. The Library
    // card has no "Edit image" button and no room for one, so its *chip* is the
    // control — and the hint says so rather than the vaguer "open it" it said
    // while the whole card was a single link to the target.
    expect(UNSTRETCHED_HINT).toContain("Click this chip");
    expect(UNSTRETCHED_HINT).not.toContain("Edit image");
    // A Gallery card already carries an "Edit image" button straight to that
    // run's editor, which since v0.390.0 opens on Auto — so name it.
    expect(UNSTRETCHED_GALLERY_HINT).toContain("Edit image");
    expect(UNSTRETCHED_GALLERY_HINT).toContain("starts you off with Auto");
  });

  it("neither tells you to press a button the editor already pressed", () => {
    // v0.390.0 made the editor open *on* Auto for a run with no saved recipe,
    // which is every card this chip is on. The Gallery's hint was written after
    // that and says "starts you off with Auto"; the Library's still said "press
    // Auto", so the two walls gave different accounts of the same screen.
    for (const hint of [UNSTRETCHED_HINT, UNSTRETCHED_GALLERY_HINT]) {
      expect(hint).toContain("Auto");
      expect(hint).not.toContain("press Auto");
    }
  });
});

describe("the Library chip's one click", () => {
  it("goes to that run's own editor, not to the target", () => {
    // The wall's card names a *target*; the editor needs a *run*, and the run
    // the card is chipped about is the one `displayed_picture_run` picked —
    // served as `UnstretchedItem.run_id` since v0.448.0.
    expect(unstretchedEditPath("M_42", 7)).toBe("/targets/M_42/edit/7");
  });

  it("degrades to a plain chip when there is no usable run id", () => {
    // Absent is not a value: a response missing the field must leave the wall
    // as it was rather than link at `…/edit/0`.
    expect(unstretchedIsLinkable(7)).toBe(true);
    expect(unstretchedIsLinkable(0)).toBe(false);
    expect(unstretchedIsLinkable(-1)).toBe(false);
    expect(unstretchedIsLinkable(undefined)).toBe(false);
    expect(unstretchedIsLinkable(null)).toBe(false);
    expect(unstretchedIsLinkable(Number.NaN)).toBe(false);
  });
});
