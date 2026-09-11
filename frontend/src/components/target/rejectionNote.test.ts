import { describe, it, expect } from "vitest";

import {
  rejectionNote,
  formatRejectPct,
  REJECTION_NOTE_MIN_FRACTION,
  REJECTION_NOTE_MAX_FRACTION,
  MIN_MAX_MIN_SAMPLES,
} from "./rejectionNote";
import rejectPctCases from "../rejectPct.cases.json";

describe("formatRejectPct", () => {
  // The *same* table `tests/test_reject_pct_mirror.py` drives
  // `seestack.stackhealth._format_reject_pct` against, so this note and the
  // "How's my stack?" note can't quote one stack two percentages. Change the
  // rule and you have to change the table, which fails both sides at once.
  it.each(rejectPctCases.cases as [number, string][])(
    "spells %p as %p, the same as the health note does",
    (fraction, want) => {
      expect(formatRejectPct(fraction)).toBe(want);
    });
});

describe("rejectionNote", () => {
  it("names a κ-σ clean-up as a percentage inside the honest band", () => {
    const note = rejectionNote("sigma-clip", 0.012);
    expect(note).toMatch(/Cleaned ~1\.2% of pixels/);
    expect(note).toMatch(/satellites/);
    expect(note).toMatch(/final image/);
  });

  it("names a drizzle-reject clean-up the same way", () => {
    expect(rejectionNote("drizzle-reject", 0.02)).toMatch(/Cleaned ~2\.0% of pixels/);
  });

  it("stays silent below the floor (nothing meaningful was rejected)", () => {
    expect(rejectionNote("sigma-clip", 0)).toBeNull();
    expect(
      rejectionNote("sigma-clip", REJECTION_NOTE_MIN_FRACTION / 2),
    ).toBeNull();
  });

  it("stays silent above the ceiling (a suspiciously large clip)", () => {
    expect(rejectionNote("sigma-clip", REJECTION_NOTE_MAX_FRACTION)).toBeNull();
    expect(rejectionNote("sigma-clip", 0.5)).toBeNull();
  });

  it("stays silent when the κ-σ fraction is unknown/invalid", () => {
    expect(rejectionNote("sigma-clip", null)).toBeNull();
    expect(rejectionNote("sigma-clip", undefined)).toBeNull();
    expect(rejectionNote("sigma-clip", NaN)).toBeNull();
  });

  it("names min/max's structural guarantee with no (misleading) percentage", () => {
    const note = rejectionNote("min-max-reject", null, 8);
    expect(note).toMatch(/only 8 subs stacked/);
    expect(note).toMatch(/brightest and darkest value at each pixel/);
    expect(note).not.toMatch(/%/);
  });

  it("withholds the guarantee below the floor, where nothing was dropped", () => {
    // Rewritten 2026-09-11 with v0.422.1's engine half; it used to pin
    // `rejectionNote("min-max-reject", null, 1)` as "only 1 sub stacked,
    // AstroStack dropped the brightest and darkest value at each pixel" — a
    // sentence that cannot be true. `MinMaxRejectAccumulator` needs three
    // samples on a pixel before there is a brightest and a darkest to spare;
    // below that it averages them all in, trail included. So the honest answer
    // is no sentence, not a softened one.
    expect(rejectionNote("min-max-reject", null, 1)).toBeNull();
    expect(rejectionNote("min-max-reject", null, MIN_MAX_MIN_SAMPLES - 1)).toBeNull();
    expect(rejectionNote("min-max-reject", null, MIN_MAX_MIN_SAMPLES))
      .toMatch(/only 3 subs stacked/);
  });

  it("min/max stays generic without a count", () => {
    const generic = rejectionNote("min-max-reject", null);
    expect(generic).toMatch(/^AstroStack dropped/);
    expect(generic).not.toMatch(/only/);
  });

  it("reads the depth, not the total, when the run's canvas is a mosaic", () => {
    // The reason min/max was picked is the *panel* depth (`_resolve_auto_reject`
    // sizes it from the thinnest substantial panel), so "because only 21 subs
    // stacked" under a four-panel mosaic names neither the reason nor the depth.
    const note = rejectionNote("min-max-reject", null, 21, 3.5);
    expect(note).toMatch(/Your 21 subs are spread across/);
    expect(note).toMatch(/about 6 subs on each part of this picture/);
    expect(note).toMatch(/brightest and darkest value at each pixel/);
    // …and a mosaic whose panels are under the floor says nothing at all.
    expect(rejectionNote("min-max-reject", null, 7, 3.5)).toBeNull();
  });

  it("is byte-for-byte unchanged on a single field and on an older backend", () => {
    const plain = rejectionNote("min-max-reject", null, 8);
    expect(rejectionNote("min-max-reject", null, 8, null)).toBe(plain);
    expect(rejectionNote("min-max-reject", null, 8, 1)).toBe(plain);
    expect(rejectionNote("min-max-reject", null, 8, undefined)).toBe(plain);
  });

  it("returns null for a plain-mean stack (no rejection pass) or unknown mode", () => {
    expect(rejectionNote(null, null)).toBeNull();
    expect(rejectionNote("", 0.02)).toBeNull();
    expect(rejectionNote("something-else", 0.02)).toBeNull();
  });
});

describe("formatRejectPct", () => {
  it("keeps a significant digit for small fractions and rounds larger ones", () => {
    // Rewritten, not deleted: this case used to pin "0.10%", which is what this
    // side printed while the "How's my stack?" note printed "0.5%"-style single
    // decimals about the same run. Two decimals is false precision on a figure
    // the sentence already prefixes with "~", so this side took the engine's
    // rule — the sliver floor included.
    expect(formatRejectPct(0.012)).toBe("1.2%");
    expect(formatRejectPct(0.001)).toBe("0.1%");
    expect(formatRejectPct(0.0007)).toBe("<0.1%");
    expect(formatRejectPct(0.153)).toBe("15%");
  });
});
