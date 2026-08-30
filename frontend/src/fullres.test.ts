import { describe, expect, it } from "vitest";
import {
  FULL_RES_PNG_MAX_LONG_EDGE, fullResPngCapped, fullResPngHint, fullResPngLabel,
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
