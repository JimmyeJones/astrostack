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

describe("where the reader is sent to see why subs were dropped", () => {
  // The Library wall's chip (v0.450.0) shows this same sentence on a card that
  // has no "rejected" count on it, so "see the count above" would point at
  // nothing. Everything else keeps the wording it has always had.

  it("defaults to the count on the page, unchanged", () => {
    const plain = thinStackWarning(1);
    expect(plain?.message).toContain('see the "rejected" count above');
    expect(thinStackWarning(1, null, "this-page")).toEqual(plain);
  });

  it("sends a wall card one click in instead", () => {
    const wall = thinStackWarning(1, null, "open-it");
    expect(wall?.message).toContain('open it and check the "rejected" count');
    expect(wall?.message).not.toContain("count above");
    // Only the pointer moves: the level, the depth and the rest of the advice
    // are the same claim about the same picture.
    expect(wall?.level).toBe(thinStackWarning(1)?.level);
    expect(wall?.frames).toBe(thinStackWarning(1)?.frames);
    expect(wall?.message).toContain("a stack only gets cleaner");
  });

  it("carries the mosaic's own two figures either way", () => {
    const wall = thinStackWarning(30, 9, "open-it");
    expect(wall?.message).toContain(
      "Your 30 subs are spread across about 9 fields of sky");
    expect(wall?.frames).toBe(3);
  });
});

describe("thinStackWarning's mosaic sentence", () => {
  it("says a typical part, because the depth it quotes is a canvas mean", () => {
    // `perPixel` divides the run's frames by the sky its canvas covers, so on a
    // raster with one deep panel and three thin ones — the owner's own shooting
    // style — there are parts on both sides of the number. Saying "each part
    // has about 3" promises the thin corner is 3 deep when it is 1.
    const w = thinStackWarning(30, 9);
    expect(w?.message).toContain("so a typical part of this picture has only about 3 subs on it");
    expect(w?.message).not.toContain("each part");
  });
});

describe("the next step when a restack would already deepen this picture", () => {
  // Found by `scripts/agent-dogfood.sh --combine`: the page said "check that
  // your subs plate-solved and weren't over-rejected … then add more subs"
  // while a sibling note had measured 3 subs accepted, located and absent from
  // this stack. Both halves of that advice are wrong in that one state.

  it("names the restack and the subs already waiting", () => {
    const w = thinStackWarning(3, null, "this-page", 3);
    expect(w?.message).toContain("This stack combined only 3 frames");
    expect(w?.message).toContain(
      "You already have 3 more subs accepted and located that this stack didn't use");
    expect(w?.message).toContain("restack to fold them in");
    expect(w?.message).toContain("No new shooting needed");
  });

  it("stops telling the reader to check solves and go shooting", () => {
    // The fail-before, as the two claims that cannot be true of subs the app
    // has already accepted and located.
    const w = thinStackWarning(3, null, "this-page", 3);
    expect(w?.message).not.toMatch(/plate-solved/);
    expect(w?.message).not.toMatch(/over-rejected/);
    expect(w?.message).not.toMatch(/add more subs/);
  });

  it("still says the picture is thin — the depth claim is unchanged", () => {
    const plain = thinStackWarning(3);
    const ready = thinStackWarning(3, null, "this-page", 7);
    expect(ready?.level).toBe(plain?.level);
    expect(ready?.frames).toBe(plain?.frames);
    expect(ready?.message).toMatch(/still look noisy/);
  });

  it("keeps the single-sub headline and swaps only the next step", () => {
    const w = thinStackWarning(1, null, "this-page", 1);
    expect(w?.level).toBe("single");
    expect(w?.message).toContain("single sub, not a stack");
    expect(w?.message).toContain(
      "You already have 1 more sub accepted and located");
    expect(w?.message).toContain("restack to fold it in");
  });

  it("carries the mosaic's own two figures, then the restack", () => {
    const w = thinStackWarning(12, 4, "this-page", 5);
    expect(w?.message).toContain(
      "Your 12 subs are spread across about 4 fields of sky");
    expect(w?.message).toContain("only about 3 subs on it");
    expect(w?.message).toContain("restack to fold them in");
  });

  it("is byte-for-byte the old warning when nothing is waiting", () => {
    // Every surface that does not have the figure, an older backend, and a
    // target that really is just thin: all read exactly as before. A nonsense
    // figure degrades the same way rather than into "0 more subs".
    const plain = thinStackWarning(3);
    for (const ready of [null, undefined, 0, -2, 0.4, NaN]) {
      expect(thinStackWarning(3, null, "this-page", ready)).toEqual(plain);
    }
    expect(plain?.message).toContain('see the "rejected" count above');
    expect(plain?.message).toContain("then add more subs");
  });

  it("leaves the wall card's pointer alone when nothing is waiting", () => {
    // The third argument still decides where the reader is sent, and the fourth
    // only ever replaces the sentence that pointer lives in.
    expect(thinStackWarning(1, null, "open-it", 0))
      .toEqual(thinStackWarning(1, null, "open-it"));
  });
});
