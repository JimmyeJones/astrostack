import { describe, it, expect } from "vitest";

import {
  rejectionNote,
  formatRejectPct,
  REJECTION_NOTE_MIN_FRACTION,
  REJECTION_NOTE_MAX_FRACTION,
} from "./rejectionNote";

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

  it("min/max singular for a one-sub context and generic without a count", () => {
    expect(rejectionNote("min-max-reject", null, 1)).toMatch(/only 1 sub stacked/);
    const generic = rejectionNote("min-max-reject", null);
    expect(generic).toMatch(/^AstroStack dropped/);
    expect(generic).not.toMatch(/only/);
  });

  it("returns null for a plain-mean stack (no rejection pass) or unknown mode", () => {
    expect(rejectionNote(null, null)).toBeNull();
    expect(rejectionNote("", 0.02)).toBeNull();
    expect(rejectionNote("something-else", 0.02)).toBeNull();
  });
});

describe("formatRejectPct", () => {
  it("keeps a significant digit for small fractions and rounds larger ones", () => {
    expect(formatRejectPct(0.012)).toBe("1.2%");
    expect(formatRejectPct(0.001)).toBe("0.10%");
    expect(formatRejectPct(0.153)).toBe("15%");
  });
});
