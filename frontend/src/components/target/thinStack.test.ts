import { describe, it, expect } from "vitest";

import { thinStackWarning, THIN_STACK_MAX_FRAMES } from "./thinStack";

describe("thinStackWarning", () => {
  it("returns null for a healthy frame count", () => {
    expect(thinStackWarning(5)).toBeNull();
    expect(thinStackWarning(50)).toBeNull();
    expect(thinStackWarning(THIN_STACK_MAX_FRAMES + 1)).toBeNull();
  });

  it("returns null when the count is unknown or invalid", () => {
    expect(thinStackWarning(null)).toBeNull();
    expect(thinStackWarning(undefined)).toBeNull();
    expect(thinStackWarning(NaN)).toBeNull();
    expect(thinStackWarning(-3)).toBeNull();
  });

  it("flags a single-frame 'stack' as not really a stack", () => {
    const w = thinStackWarning(1);
    expect(w?.level).toBe("single");
    expect(w?.frames).toBe(1);
    expect(w?.message).toMatch(/single sub/);
    expect(w?.message).toMatch(/plate-solved/);
  });

  it("treats a zero-frame stack as the single (most severe) level", () => {
    expect(thinStackWarning(0)?.level).toBe("single");
  });

  it("flags a very thin (2–4 frame) stack as noisy but distinct from single", () => {
    for (const n of [2, 3, 4]) {
      const w = thinStackWarning(n);
      expect(w?.level).toBe("thin");
      expect(w?.frames).toBe(n);
      expect(w?.message).toMatch(new RegExp(`only ${n} frames`));
    }
  });

  // A mosaic spreads its subs across the raster, so the run's frame count is not
  // the depth of the picture. Nine subs over a 3x3 is one sub everywhere — the
  // exact speckle this warning exists for, and it stayed silent because 9 > 4.
  describe("on a mosaic the threshold is a depth, not a count", () => {
    it("warns about a mosaic that is one sub deep everywhere", () => {
      const w = thinStackWarning(9, 9);
      expect(w?.level).toBe("single");
      expect(w?.frames).toBe(1);
      // Both figures, because a page that says "27 subs" and "only 1 sub" has
      // told the reader two things that can't both be true on their own.
      expect(w?.message).toMatch(/9 subs are spread across about 9 fields of sky/);
      expect(w?.message).toMatch(/only about 1 sub on it/);
      expect(w?.message).toMatch(/single sub, not a stack/);
    });

    it("warns about a mosaic that is 2-4 subs deep", () => {
      const w = thinStackWarning(12, 4);
      expect(w?.level).toBe("thin");
      expect(w?.frames).toBe(3);
      expect(w?.message).toMatch(/only about 3 subs on it/);
      expect(w?.message).toMatch(/still look noisy/);
    });

    it("stays quiet about a mosaic that is genuinely deep", () => {
      // 400 subs over a 2x2 is 100 a panel — a fine picture, and the count and
      // the depth agree that it is.
      expect(thinStackWarning(400, 4)).toBeNull();
      // The dogfood mosaic sample: 21 subs, ~3.5 fields, ~6 deep — which is what
      // the app's own health panel says about that picture ("most of it has 6").
      expect(thinStackWarning(21, 3.5)).toBeNull();
    });

    it("would have said nothing about either of those without the figure", () => {
      // The fail-before, stated as a property: the count alone clears the bar in
      // every case above, which is exactly why the warning never fired.
      expect(thinStackWarning(9)).toBeNull();
      expect(thinStackWarning(12)).toBeNull();
    });

    it("is byte-for-byte the single-field warning for any non-mosaic figure", () => {
      // null / absent / at-or-below-1 all mean "no correction" — an older
      // backend, and every single-field target, read exactly as before.
      const plain = thinStackWarning(3);
      for (const ff of [null, undefined, 0, 0.5, 1]) {
        expect(thinStackWarning(3, ff)).toEqual(plain);
      }
      expect(plain?.message).toMatch(/This stack combined only 3 frames/);
    });
  });
});
