import { describe, expect, it } from "vitest";
import { sharpestYet, SHARPEST_MARGIN } from "./sharpestYet";

// Helper: a run with just the fields the beat reads.
const run = (fwhm: number | null, date = "2026-07-20T00:00:00Z") => ({
  timestamp_utc: date,
  stack_fwhm_px: fwhm,
});

describe("sharpestYet", () => {
  it("returns null for the first run (no prior to beat)", () => {
    expect(sharpestYet([run(2.5)])).toBeNull();
    expect(sharpestYet([])).toBeNull();
    expect(sharpestYet(null)).toBeNull();
    expect(sharpestYet(undefined)).toBeNull();
  });

  it("celebrates a clearly sharper newest run with the right prior + date", () => {
    const beat = sharpestYet([
      run(2.1, "2026-07-24T22:00:00Z"), // newest = current
      run(2.6, "2026-07-12T21:00:00Z"),
      run(2.9, "2026-07-05T20:00:00Z"),
    ]);
    expect(beat).not.toBeNull();
    expect(beat!.currentFwhmPx).toBe(2.1);
    expect(beat!.priorBestFwhmPx).toBe(2.6); // the sharpest prior, not the latest prior
    expect(beat!.priorBestDate).toBe("2026-07-12T21:00:00Z");
  });

  it("returns null when the newest run is worse than a prior best", () => {
    expect(sharpestYet([run(3.0), run(2.4), run(2.8)])).toBeNull();
  });

  it("returns null on a tie / within-noise improvement (strictly-better-by-a-margin only)", () => {
    // Exactly equal.
    expect(sharpestYet([run(2.5), run(2.5)])).toBeNull();
    // Just under the margin — 1% sharper, below the 2% floor.
    const barelyBetter = 2.5 * (1 - SHARPEST_MARGIN / 2);
    expect(sharpestYet([run(barelyBetter), run(2.5)])).toBeNull();
    // Just over the margin — 3% sharper, clears the floor.
    const clearlyBetter = 2.5 * (1 - SHARPEST_MARGIN * 1.5);
    expect(sharpestYet([run(clearlyBetter), run(2.5)])).not.toBeNull();
  });

  it("ignores prior runs with no FWHM measurement and stays silent when none measured", () => {
    // Only prior measured run is 2.8 → current 2.2 beats it.
    const beat = sharpestYet([run(2.2), run(null), run(2.8), run(null)]);
    expect(beat!.priorBestFwhmPx).toBe(2.8);
    // No prior has a measurement → nothing to beat.
    expect(sharpestYet([run(2.2), run(null), run(null)])).toBeNull();
  });

  it("returns null when the current run has no FWHM measurement", () => {
    expect(sharpestYet([run(null), run(2.5)])).toBeNull();
  });

  it("ignores non-finite / non-positive FWHM values", () => {
    expect(sharpestYet([run(2.0), run(0), run(-1), run(NaN)])).toBeNull();
    expect(sharpestYet([run(NaN), run(2.5)])).toBeNull();
  });
});
