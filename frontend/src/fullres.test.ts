import { describe, expect, it } from "vitest";
import {
  FULL_RES_PNG_MAX_LONG_EDGE, FULL_RES_SLOW_PIXELS, fullResDownloadHint, fullResPngCapped,
  fullResPngHint, fullResPngLabel, fullResPreparingNotice,
} from "./fullres";

const CAP = FULL_RES_PNG_MAX_LONG_EDGE;

// Four screens describe the "Full-res PNG" download, and until this shipped all
// four called it native size — History printed the exact canvas dimensions. The
// endpoint decimates anything past `CAP` on its long edge, so on a big union
// mosaic (the picture where it matters) the sentence was false. These pin the
// one place that sentence is now written.
describe("what the full-res PNG download actually is", () => {
  it("is native for an ordinary Seestar canvas", () => {
    expect(fullResPngCapped(1080, 1920)).toBe(false);
    expect(fullResPngLabel(1080, 1920)).toBe("Full-res PNG (native size)");
    expect(fullResPngHint(1080, 1920)).toBe("Same look, full size (1080×1920 px)");
  });

  it("stops claiming native size once the render caps it", () => {
    const w = CAP + 2000;
    expect(fullResPngCapped(w, 4000)).toBe(true);
    expect(fullResPngLabel(w, 4000)).toBe(`Full-res PNG (up to ${CAP} px)`);
    // The hint names the canvas it was capped *from*, and points at the two
    // files that do hold those pixels.
    const hint = fullResPngHint(w, 4000);
    expect(hint).toContain(`up to ${CAP} px`);
    expect(hint).toContain(`${w}×4000`);
    expect(hint).toMatch(/FITS or TIFF/);
    expect(hint).not.toContain("full size");
  });

  it("caps on the *long* edge, so a tall canvas counts too", () => {
    expect(fullResPngCapped(200, CAP + 1)).toBe(true);
    expect(fullResPngCapped(CAP + 1, 200)).toBe(true);
  });

  it("treats a canvas exactly at the cap as native — the render does", () => {
    expect(fullResPngCapped(CAP, CAP)).toBe(false);
    expect(fullResPngLabel(CAP, CAP)).toBe("Full-res PNG (native size)");
  });

  it("words it the common way when the dimensions aren't known", () => {
    // A surface (or an older backend) that doesn't carry the canvas must not
    // warn about a cap it has no evidence for — nor quote dimensions it lacks.
    expect(fullResPngCapped(undefined, undefined)).toBe(false);
    expect(fullResPngCapped(0, 0)).toBe(false);
    expect(fullResPngLabel()).toBe("Full-res PNG (native size)");
    expect(fullResPngHint()).toBe("Same look, full size");
    expect(fullResPngHint(0, 0)).toBe("Same look, full size");
  });
});

// Owner ⭐ 2026-10-28: the Full-res PNG "takes a super long time". A download
// link shows nothing until the first byte, so a big mosaic's click looked dead
// and invited a second click. The notice says it is coming; a small field,
// which arrives in about a second, gets none.
describe("the notice while a big full-res picture is prepared", () => {
  it("says nothing for an ordinary Seestar field", () => {
    expect(fullResPreparingNotice(1080, 1920)).toBeNull();
  });

  it("names the size and says not to click again on a big mosaic", () => {
    const msg = fullResPreparingNotice(3494, 2470);
    expect(msg).toContain("3494×2470");
    expect(msg).toMatch(/no need to click again/);
    expect(3494 * 2470).toBeGreaterThan(FULL_RES_SLOW_PIXELS);
  });

  it("still speaks when the size is unknown", () => {
    expect(fullResPreparingNotice()).toMatch(/^A big picture can take a minute/);
    expect(fullResPreparingNotice(null, 1200)).not.toBeNull();
  });
});

describe("fullResDownloadHint — the file's own size once the server says it", () => {
  it("keeps the canvas sentence until there is an answer", () => {
    expect(fullResDownloadHint(1080, 1920)).toBe(fullResPngHint(1080, 1920));
    expect(fullResDownloadHint(1080, 1920, null)).toBe(fullResPngHint(1080, 1920));
    expect(fullResDownloadHint(1080, 1920, { width: null, height: null, trimmed: false }))
      .toBe(fullResPngHint(1080, 1920));
  });

  it("prints the trimmed size of an unedited mosaic, not its canvas", () => {
    const hint = fullResDownloadHint(907, 615, { width: 875, height: 587, trimmed: true });
    expect(hint).toBe("Same look, ragged mosaic border trimmed (875×587 px)");
    expect(hint).not.toContain("907");
  });

  it("prints an edit's own cropped size", () => {
    expect(fullResDownloadHint(400, 300, { width: 146, height: 138, trimmed: false }))
      .toBe("Same look, full size (146×138 px)");
  });

  it("leaves a capped canvas's explanation alone", () => {
    const w = FULL_RES_PNG_MAX_LONG_EDGE + 4000;
    expect(fullResDownloadHint(w, 4000, { width: 8000, height: 2667, trimmed: false }))
      .toBe(fullResPngHint(w, 4000));
  });
});
