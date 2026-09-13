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

describe("rejectionBadge — the depth every pass has and the chip used to skip", () => {
  // v0.422.1 established that each rejection method removes nothing below a
  // per-pixel sample depth, and corrected the three surfaces that make a
  // *verdict* about one run. This chip renders in a list from stored options
  // alone, so it states the method's rule instead — true of every run, and so
  // never in conflict with the header's own REJREACH answer on the same card.

  it("says min/max needs 3 subs on a pixel before it has extremes to spare", () => {
    const t = rejectionBadge({ min_max_reject: true })?.title ?? "";
    // The guarantee is kept — nothing removed — and its precondition added.
    expect(t).toMatch(/removes a lone satellite \/ plane trail/);
    expect(t).toMatch(/needs 3 subs on a pixel/);
    expect(t).toMatch(/averaged in as they are/);
  });

  it("scales that depth with a top/bottom-k trim, as 2k+1", () => {
    // The number the Stack form's own copy uses: a trim of k needs 2k+1 samples
    // on a pixel to fully apply.
    expect(rejectionBadge({ min_max_reject: true, min_max_reject_count: 3 })?.title)
      .toMatch(/needs 7 subs on a pixel/);
    expect(rejectionBadge({ min_max_reject: true, min_max_reject_count: 2 })?.title)
      .toMatch(/needs 5 subs on a pixel/);
  });

  it("names the run's OWN κ bound, not the default's, for κ-σ", () => {
    expect(rejectionBadge({ sigma_clip: true, sigma_kappa: 3 })?.title)
      .toMatch(/about 11 subs overlap on one pixel/);
    // A gentler κ reaches a lone trail far sooner; quoting 11 there would be a
    // second untruth in place of the first.
    expect(rejectionBadge({ sigma_clip: true, sigma_kappa: 1.5 })?.title)
      .toMatch(/about 4 subs overlap on one pixel/);
    // No stored κ reads as the app default, exactly as the label beside it does.
    expect(rejectionBadge({ sigma_clip: true })?.title)
      .toMatch(/about 11 subs overlap on one pixel/);
  });

  it("gives drizzle's own clip the same bound, because it is the same clip", () => {
    // `lone_outlier_min_depth` returns κ-σ's floor for "drizzle-reject" too —
    // measured on a real drizzle stack — and this is the owner's case: he
    // drizzles mosaics, whose panels are thin.
    const t = rejectionBadge({ drizzle: true, drizzle_scale: 2, drizzle_reject: true,
                               sigma_kappa: 3 })?.title ?? "";
    expect(t).toMatch(/rejecting satellites, planes and cosmic rays/);
    expect(t).toMatch(/about 11 subs overlap on one pixel/);
  });

  it("says nothing about reach on a drizzle run with its clip switched off", () => {
    // There is no pass to describe the reach of — the existing sentence already
    // says no rejection ran, and adding a bound would imply one did.
    const t = rejectionBadge({ drizzle: true, drizzle_scale: 2 })?.title ?? "";
    expect(t).toMatch(/No per-pixel outlier rejection/);
    expect(t).not.toMatch(/subs overlap on one pixel/);
  });

  it("says the count is per panel on a mosaic, wherever it names one", () => {
    // The substitution this whole family exists to undo: a target's frame total
    // is not a pixel's depth, and every one of these bounds is per pixel.
    for (const opts of [
      { sigma_clip: true, sigma_kappa: 3 },
      { drizzle: true, drizzle_reject: true },
    ]) {
      expect(rejectionBadge(opts)?.title).toMatch(/the subs on one panel, not the total/);
    }
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
