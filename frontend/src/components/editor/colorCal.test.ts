import { describe, expect, it } from "vitest";

import { autoColorCalCaption } from "./colorCal";

describe("autoColorCalCaption", () => {
  it("returns null when unavailable or the mode is unknown", () => {
    expect(autoColorCalCaption(undefined)).toBeNull();
    expect(autoColorCalCaption(null)).toBeNull();
    expect(autoColorCalCaption({ mode_used: "", n_stars_used: 0 })).toBeNull();
    expect(
      autoColorCalCaption({ mode_used: "something_new", n_stars_used: 3 }),
    ).toBeNull();
  });

  it("reports a star-based solve with the star count (reassuring)", () => {
    const cc = autoColorCalCaption({ mode_used: "gray_star", n_stars_used: 240 });
    expect(cc).not.toBeNull();
    expect(cc!.neutral).toBe(true);
    expect(cc!.text).toContain("240 stars");
    // gaia reads the same way.
    expect(
      autoColorCalCaption({ mode_used: "gaia", n_stars_used: 55 })!.text,
    ).toContain("55 stars");
  });

  it("singularises a single star", () => {
    const cc = autoColorCalCaption({ mode_used: "gray_star", n_stars_used: 1 });
    expect(cc!.text).toContain("1 star ");
    expect(cc!.text).not.toContain("1 stars");
  });

  it("never claims '0 stars' for a star-based mode", () => {
    const cc = autoColorCalCaption({ mode_used: "gray_star", n_stars_used: 0 });
    expect(cc!.neutral).toBe(true);
    expect(cc!.text).not.toContain("0 star");
  });

  it("names the background-neutral fallback (reassuring, too few stars)", () => {
    const cc = autoColorCalCaption({
      mode_used: "background_neutral",
      n_stars_used: 0,
    });
    expect(cc!.neutral).toBe(true);
    expect(cc!.text).toContain("background");
    expect(cc!.text).toContain("too few stars");
  });

  it("advises the editor fix when Auto couldn't white-balance at all", () => {
    const cc = autoColorCalCaption({ mode_used: "none", n_stars_used: 0 });
    expect(cc!.neutral).toBe(false);
    expect(cc!.text).toContain("Neutralize background");
  });

  it("appends a clamp note when the backend capped an extreme channel", () => {
    const star = autoColorCalCaption({
      mode_used: "gray_star",
      n_stars_used: 240,
      notes: "gray-world over detected stars (clamped an out-of-range channel scale)",
    });
    expect(star!.neutral).toBe(true);
    expect(star!.text).toContain("240 stars");
    expect(star!.text).toContain("capped an extreme channel");
    // The background-neutral fallback can clamp too.
    const bg = autoColorCalCaption({
      mode_used: "background_neutral",
      n_stars_used: 0,
      notes: "neutralised sky background (clamped an out-of-range channel scale)",
    });
    expect(bg!.text).toContain("capped an extreme channel");
  });

  it("does not add the clamp note when nothing was clamped", () => {
    const cc = autoColorCalCaption({
      mode_used: "gray_star",
      n_stars_used: 240,
      notes: "gray-world over detected stars",
    });
    expect(cc!.text).not.toContain("capped an extreme channel");
    // Absent notes is fine too.
    expect(
      autoColorCalCaption({ mode_used: "gray_star", n_stars_used: 12 })!.text,
    ).not.toContain("capped an extreme channel");
  });
});
