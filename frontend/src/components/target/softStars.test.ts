import { describe, it, expect } from "vitest";
import { softerThanUsual, SOFT_STAR_MARGIN, SOFT_STAR_MIN_PRIORS } from "./softStars";

const run = (fwhm: number | null) => ({ stack_fwhm_px: fwhm });

describe("softerThanUsual", () => {
  it("returns null with no runs / a single run (no history to compare)", () => {
    expect(softerThanUsual(null)).toBeNull();
    expect(softerThanUsual([])).toBeNull();
    expect(softerThanUsual([run(4.0)])).toBeNull();
  });

  it("returns null until there are enough measured priors", () => {
    // Current soft, but only one prior measured → below the min-priors floor.
    expect(softerThanUsual([run(6.0), run(3.0)])).toBeNull();
    // A second measured prior unlocks the comparison.
    const soft = softerThanUsual([run(6.0), run(3.0), run(3.0)]);
    expect(soft).not.toBeNull();
    expect(SOFT_STAR_MIN_PRIORS).toBe(2);
  });

  it("flags a run materially softer than the target's usual (median prior)", () => {
    // Usual = median(2.9, 3.0, 3.1) = 3.0; current 4.5 is 50% larger → soft.
    const soft = softerThanUsual([run(4.5), run(3.0), run(2.9), run(3.1)]);
    expect(soft).not.toBeNull();
    expect(soft?.currentFwhmPx).toBe(4.5);
    expect(soft?.typicalFwhmPx).toBe(3.0);
  });

  it("uses the median so a single flukey prior doesn't move 'usual'", () => {
    // Priors 3.0, 3.1, 9.0 → median 3.1 (not the mean ~5.0). Current 3.9 is only
    // ~26% over the median → just soft; against a mean it would look fine.
    const soft = softerThanUsual([run(3.9), run(3.0), run(3.1), run(9.0)]);
    expect(soft?.typicalFwhmPx).toBe(3.1);
  });

  it("stays silent within the normal band (ordinary seeing variation)", () => {
    // Current 3.5 vs usual 3.0 → 16.7% over, below the 25% margin → null.
    expect(softerThanUsual([run(3.5), run(3.0), run(3.0)])).toBeNull();
    // Exactly at the margin is not "materially" softer → null.
    expect(softerThanUsual([run(3.0 * (1 + SOFT_STAR_MARGIN)), run(3.0), run(3.0)])).toBeNull();
    // Sharper than usual is obviously not soft.
    expect(softerThanUsual([run(2.5), run(3.0), run(3.0)])).toBeNull();
  });

  it("ignores unmeasured / non-finite / non-positive values", () => {
    // Current unmeasured → null even though priors are fine.
    expect(softerThanUsual([run(null), run(3.0), run(3.0)])).toBeNull();
    // Unmeasured priors don't count toward the min-priors floor.
    expect(softerThanUsual([run(6.0), run(3.0), run(null), run(NaN as unknown as number)])).toBeNull();
    // With enough measured priors it fires, skipping the junk ones.
    const soft = softerThanUsual([run(6.0), run(3.0), run(0), run(-1), run(3.0)]);
    expect(soft?.typicalFwhmPx).toBe(3.0);
  });
});
