import { describe, it, expect } from "vitest";
import { focusChips } from "./focusChips";

// Minimal run shape: id + timestamp + measured FWHM (native-frame px). Runs are
// passed newest-first, exactly as `listStackRuns` returns them.
const run = (id: number, fwhm: number | null, ts = `2026-07-${String(id).padStart(2, "0")}T00:00:00`) => ({
  id,
  timestamp_utc: ts,
  stack_fwhm_px: fwhm,
});

describe("focusChips", () => {
  it("returns an empty map for null / empty input", () => {
    expect(focusChips(null).size).toBe(0);
    expect(focusChips(undefined).size).toBe(0);
    expect(focusChips([]).size).toBe(0);
  });

  it("gives no chip to the oldest run (it has no priors)", () => {
    // Two runs; the older one (index 1) can never earn a chip.
    const chips = focusChips([run(2, 4.0), run(1, 3.0)]);
    expect(chips.has(1)).toBe(false);
  });

  it("flags a new personal-best FWHM as 'sharpest'", () => {
    // Newest (id 3) at 2.5 beats both priors (3.0, 3.2) → sharpest.
    const chips = focusChips([run(3, 2.5), run(2, 3.0), run(1, 3.2)]);
    expect(chips.get(3)).toBe("sharpest");
  });

  it("flags a run materially softer than the target's usual as 'soft'", () => {
    // Newest (id 4) at 4.5 vs median prior 3.0 → 50% over → soft. Needs ≥2
    // measured priors (SOFT_STAR_MIN_PRIORS), which the three priors supply.
    const chips = focusChips([run(4, 4.5), run(3, 3.0), run(2, 2.9), run(1, 3.1)]);
    expect(chips.get(4)).toBe("soft");
  });

  it("judges each row against only its own priors (older runs)", () => {
    // Chronology newest→oldest: 2.4 (id4), 4.6 (id3), 3.0 (id2), 3.0 (id1).
    // - id4 (2.4) beats every prior → sharpest.
    // - id3 (4.6) vs median(3.0, 3.0)=3.0 → soft (its priors are only id2,id1).
    // - id2 (3.0) has one prior (id1) → below the 2-prior floor → no chip.
    const chips = focusChips([run(4, 2.4), run(3, 4.6), run(2, 3.0), run(1, 3.0)]);
    expect(chips.get(4)).toBe("sharpest");
    expect(chips.get(3)).toBe("soft");
    expect(chips.has(2)).toBe(false);
    expect(chips.has(1)).toBe(false);
  });

  it("stays silent within the normal band and on unmeasured runs", () => {
    // 3.4 vs usual 3.0 is ~13% over — below the 25% soft margin, and not a
    // record → no chip. And a null-FWHM run earns nothing.
    const chips = focusChips([run(3, 3.4), run(2, 3.0), run(1, 3.0)]);
    expect(chips.has(3)).toBe(false);
    const none = focusChips([run(2, null), run(1, 3.0)]);
    expect(none.has(2)).toBe(false);
  });
});
