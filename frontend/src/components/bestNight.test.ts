import { describe, expect, it } from "vitest";
import { bestNightLines } from "./bestNight";
import { formatIntegration } from "../format";
import type { NightActivity } from "../api/client";

function night(over: Partial<NightActivity> = {}): NightActivity {
  return {
    date: "2026-01-12",
    exposure_s: 5400,
    n_frames: 180,
    targets: ["M 42"],
    median_fwhm_px: 2.44,
    n_measured: 180,
    ...over,
  };
}

describe("bestNightLines", () => {
  it("names the night, the star size and what was pointed at", () => {
    const l = bestNightLines(night(), formatIntegration);
    expect(l).not.toBeNull();
    expect(l!.date).toBe("12 Jan 2026");
    // Smaller is sharper, and pixels are the unit the Frames table, the Nights
    // card and the session recap all already use.
    expect(l!.value).toBe("2.4 px stars");
    expect(l!.detail).toContain("on M 42");
    expect(l!.detail).toContain("180 subs measured");
  });

  it("names both targets on a two-target night and counts beyond that", () => {
    expect(bestNightLines(night({ targets: ["M 42", "M 31"] }), formatIntegration)!.detail)
      .toContain("on M 42 and M 31");
    expect(
      bestNightLines(night({ targets: ["A", "B", "C"] }), formatIntegration)!.detail,
    ).toContain("across 3 targets");
  });

  it("says nothing at all when the backend named no best night", () => {
    // The server stays silent until enough nights carry enough measured subs;
    // the card must render nothing rather than hedge.
    expect(bestNightLines(null, formatIntegration)).toBeNull();
    expect(bestNightLines(undefined, formatIntegration)).toBeNull();
  });

  it("says nothing when the field is missing or unusable", () => {
    // An older backend sends no median at all; a zero would be a failed
    // measurement, not a perfect one.
    expect(bestNightLines(night({ median_fwhm_px: undefined }), formatIntegration))
      .toBeNull();
    expect(bestNightLines(night({ median_fwhm_px: null }), formatIntegration))
      .toBeNull();
    expect(bestNightLines(night({ median_fwhm_px: 0 }), formatIntegration)).toBeNull();
  });

  it("still reads sensibly with no targets or exposure recorded", () => {
    const l = bestNightLines(
      night({ targets: [], exposure_s: 0, n_measured: 0 }), formatIntegration);
    expect(l).not.toBeNull();
    expect(l!.detail).toBe("Your steadiest sky yet.");
  });
});
