import { describe, it, expect } from "vitest";
import { rejectionBadge, combineMethodKey } from "./RejectionBadge";

describe("rejectionBadge", () => {
  it("returns null for a plain mean (no rejection)", () => {
    expect(rejectionBadge({})).toBeNull();
    expect(rejectionBadge({ sigma_clip: false })).toBeNull();
    expect(rejectionBadge(null)).toBeNull();
    expect(rejectionBadge(undefined)).toBeNull();
  });

  it("labels sigma-clip with its kappa", () => {
    expect(rejectionBadge({ sigma_clip: true, sigma_kappa: 3 })?.label).toBe("σ-clip κ3");
    expect(rejectionBadge({ sigma_clip: true, sigma_kappa: 2.5 })?.label).toBe("σ-clip κ2.5");
    // default kappa when unspecified
    expect(rejectionBadge({ sigma_clip: true })?.label).toBe("σ-clip κ3");
  });

  it("labels min/max rejection", () => {
    expect(rejectionBadge({ min_max_reject: true })?.label).toBe("min-max");
    // Explicit default count still reads as the plain single-drop label.
    expect(rejectionBadge({ min_max_reject: true, min_max_reject_count: 1 })?.label)
      .toBe("min-max");
  });

  it("shows the k count for a top/bottom-k trim (k>1)", () => {
    expect(rejectionBadge({ min_max_reject: true, min_max_reject_count: 3 })?.label)
      .toBe("min-max ×3");
  });

  it("min/max takes precedence over sigma-clip (engine ignores κ-σ then)", () => {
    expect(
      rejectionBadge({ min_max_reject: true, sigma_clip: true, sigma_kappa: 3 })?.label,
    ).toBe("min-max");
  });

  it("labels drizzle with its scale and wins over everything", () => {
    expect(rejectionBadge({ drizzle: true, drizzle_scale: 2 })?.label).toBe("drizzle ×2");
    expect(rejectionBadge({ drizzle: true, drizzle_scale: 1.5 })?.label).toBe("drizzle ×1.5");
    expect(
      rejectionBadge({ drizzle: true, drizzle_scale: 2, min_max_reject: true, sigma_clip: true })
        ?.label,
    ).toBe("drizzle ×2");
  });

  it("mentions rejection in the drizzle tooltip only when drizzle_reject is on", () => {
    expect(rejectionBadge({ drizzle: true })?.title).not.toMatch(/outlier rejection\)/);
    expect(rejectionBadge({ drizzle: true, drizzle_reject: true })?.title).toMatch(
      /outlier rejection/,
    );
  });

  it("returns null for editor-recipe and channel-combine runs", () => {
    expect(rejectionBadge({ editor_recipe: [], sigma_clip: true })).toBeNull();
    expect(rejectionBadge({ channel_combine: {}, drizzle: true })).toBeNull();
  });

  it("notes in the tooltip when the method was auto-picked", () => {
    // The resolved method still drives the label; auto_reject only enriches the
    // tooltip so the user knows it was chosen for them.
    const mm = rejectionBadge({ auto_reject: true, min_max_reject: true });
    expect(mm?.label).toBe("min-max");
    expect(mm?.title).toMatch(/Auto outlier removal picked this/);
    const sc = rejectionBadge({ auto_reject: true, sigma_clip: true, sigma_kappa: 3 });
    expect(sc?.label).toBe("σ-clip κ3");
    expect(sc?.title).toMatch(/Auto outlier removal picked this/);
    // Without auto_reject the tooltip carries no such note.
    expect(rejectionBadge({ min_max_reject: true })?.title).not.toMatch(/Auto outlier removal/);
  });
});

describe("combineMethodKey", () => {
  it("collapses to a coarse key with the same precedence as the badge", () => {
    expect(combineMethodKey({ drizzle: true, min_max_reject: true, sigma_clip: true })).toBe("drizzle");
    expect(combineMethodKey({ min_max_reject: true, sigma_clip: true })).toBe("min-max");
    expect(combineMethodKey({ sigma_clip: true, sigma_kappa: 2.5 })).toBe("sigma-clip");
  });

  it("returns 'mean' (not null) for a plain average, so it's a filterable category", () => {
    expect(combineMethodKey({})).toBe("mean");
    expect(combineMethodKey({ sigma_clip: false })).toBe("mean");
  });

  it("returns null for editor/channel-combine runs and missing options", () => {
    expect(combineMethodKey({ editor_recipe: [], sigma_clip: true })).toBeNull();
    expect(combineMethodKey({ channel_combine: {}, drizzle: true })).toBeNull();
    expect(combineMethodKey(null)).toBeNull();
    expect(combineMethodKey(undefined)).toBeNull();
  });
});
