import { describe, expect, it } from "vitest";
import { tiffDownloadHint, tiffOpensAsShown } from "./tiffDownload";

// The TIFF item was the one download on History's menu with nothing said about
// it, and the one a beginner is most likely to be surprised by: a plain stack's
// TIFF is linear, so it opens near-black and reads as a broken file.
describe("what the TIFF download opens as", () => {
  it("warns for an ordinary stack, whose TIFF is linear", () => {
    expect(tiffOpensAsShown({})).toBe(false);
    expect(tiffDownloadHint({})).toMatch(/opens dark/);
  });

  it("does not warn about an editor export, which is the finished picture", () => {
    // Written by the same call that passes `already_display=True`, so this flag
    // and the file's contents cannot disagree.
    const opts = { editor_recipe: { ops: [] }, display_space: true };
    expect(tiffOpensAsShown(opts)).toBe(true);
    expect(tiffDownloadHint(opts)).toBe("16-bit — the finished picture, at full depth");
  });

  it("does not warn when the stack itself baked the stretch in", () => {
    expect(tiffOpensAsShown({ tiff_mode: "autostretch" })).toBe(true);
    // …and the stacker's default mode is the one that needs the warning.
    expect(tiffOpensAsShown({ tiff_mode: "linear" })).toBe(false);
  });

  it("says the safe thing when the run carries no options at all", () => {
    // Missing/unparseable options land here. Warning about a picture that turns
    // out fine costs nothing; staying silent about a linear one costs the whole
    // download, so the default is the warning.
    expect(tiffOpensAsShown(undefined)).toBe(false);
    expect(tiffOpensAsShown(null)).toBe(false);
    expect(tiffDownloadHint(undefined)).toMatch(/opens dark/);
  });

  it("is not fooled by a falsy or non-boolean flag", () => {
    expect(tiffOpensAsShown({ display_space: false })).toBe(false);
    expect(tiffOpensAsShown({ display_space: "true" })).toBe(false);
    expect(tiffOpensAsShown({ tiff_mode: "something-else" })).toBe(false);
  });
});
