import { describe, it, expect } from "vitest";
import { rejectionBadge } from "./RejectionBadge";

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
});
