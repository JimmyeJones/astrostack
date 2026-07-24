import { describe, expect, it } from "vitest";

import { memoryFixAction } from "./stackMemoryFix";

describe("memoryFixAction", () => {
  it("returns null when there is no fix", () => {
    expect(memoryFixAction(null)).toBeNull();
    expect(memoryFixAction(undefined)).toBeNull();
  });

  it("maps a drizzle-scale fix to setting drizzle_scale, naming the peak", () => {
    const action = memoryFixAction({
      kind: "drizzle_scale",
      value: 1.3,
      peak_bytes: 1_400_000_000,
      peak_gb: 1.4,
    });
    expect(action).toEqual({
      label: "Use drizzle ×1.3 instead — fits at ~1.4 GB",
      optionKey: "drizzle_scale",
      optionValue: 1.3,
    });
  });

  it("maps a reduce-outlier-passes fix to min_max_reject_count = 1", () => {
    const action = memoryFixAction({
      kind: "reduce_outlier_passes",
      value: null,
      peak_bytes: 770_000_000,
      peak_gb: 0.77,
    });
    // Sub-1 GB peaks keep two decimals so a tiny fit isn't rounded to "~0.8 GB".
    expect(action).toEqual({
      label: "Lower Extra outlier passes to 1 — fits at ~0.77 GB",
      optionKey: "min_max_reject_count",
      optionValue: 1,
    });
  });

  it("maps a reference-canvas fix to mosaic_canvas = reference", () => {
    const action = memoryFixAction({
      kind: "reference_canvas",
      value: null,
      peak_bytes: 1_200_000_000,
      peak_gb: 1.2,
    });
    expect(action).toEqual({
      label: "Use the reference canvas instead — fits at ~1.2 GB",
      optionKey: "mosaic_canvas",
      optionValue: "reference",
    });
  });

  it("returns null for a malformed drizzle-scale fix with no value", () => {
    expect(
      memoryFixAction({ kind: "drizzle_scale", value: null, peak_bytes: 1, peak_gb: 0.01 }),
    ).toBeNull();
  });
});
