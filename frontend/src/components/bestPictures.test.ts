import { describe, expect, it } from "vitest";
import { bestPictureClauses, bestPictureReason, isPinnedPick, pinnedNote } from "./bestPictures";
import type { BestPicture } from "../api/client";

function pic(over: Partial<BestPicture>): BestPicture {
  return {
    safe: "m31",
    target_name: "M31",
    run_id: 1,
    output_basename: "master",
    timestamp_utc: "2026-05-02T00:00:00Z",
    n_frames_used: 500,
    canvas_w: 480,
    canvas_h: 320,
    total_exposure_s: 12240, // 3.4 h
    noise_sigma: 0.02,
    has_preview: true,
    has_fits: false,
    has_tiff: false,
    preview_url: "/api/targets/m31/stack-runs/1/preview",
    score: 1,
    ...over,
  };
}

describe("bestPictureReason", () => {
  it("joins integration time and frame count", () => {
    expect(bestPictureReason(pic({}))).toBe("3.4 h · 500 frames");
  });

  it("singularises a one-frame count", () => {
    expect(bestPictureClauses(pic({ n_frames_used: 1 }))).toContain("1 frame");
  });

  it("drops the integration clause for an old run with no exposure", () => {
    expect(bestPictureReason(pic({ total_exposure_s: null }))).toBe("500 frames");
  });

  it("drops a non-finite / non-positive exposure", () => {
    expect(bestPictureReason(pic({ total_exposure_s: 0 }))).toBe("500 frames");
    expect(bestPictureReason(pic({ total_exposure_s: NaN }))).toBe("500 frames");
  });

  it("returns empty when the run carries neither metric", () => {
    expect(bestPictureClauses(pic({ total_exposure_s: null, n_frames_used: 0 }))).toEqual([]);
    expect(bestPictureReason(pic({ total_exposure_s: null, n_frames_used: 0 }))).toBe("");
  });
});

// The caption's two clauses are the *target's* totals. A mosaic spreads its subs
// across the raster, so on a 3x3 "3.4 h · 500 frames" is about 23 min and 55
// subs anywhere you look — and this line is the wall's stated reason the picture
// is one of someone's best. The run's own `field_fulls` says which number is
// which; a single field and an older backend keep today's wording exactly.
describe("bestPictureReason on a canvas bigger than one field of sky", () => {
  it("says what one patch of sky actually got, keeping both totals", () => {
    expect(bestPictureReason(pic({ field_fulls: 4 }))).toBe(
      "3.4 h \u00b7 500 frames \u00b7 about 51 min on each patch of sky",
    );
  });

  it("scopes a nine-field raster by its own scale, not a fixed guess", () => {
    expect(bestPictureReason(pic({ field_fulls: 9 }))).toBe(
      "3.4 h \u00b7 500 frames \u00b7 about 23 min on each patch of sky",
    );
  });

  it("falls back to the sub depth when the run recorded no integration time", () => {
    expect(bestPictureReason(pic({ total_exposure_s: null, field_fulls: 4 }))).toBe(
      "500 frames \u00b7 about 125 subs on each patch of sky",
    );
  });

  it("keeps today's wording on a single field and on an older backend", () => {
    const plain = "3.4 h \u00b7 500 frames";
    expect(bestPictureReason(pic({}))).toBe(plain);
    expect(bestPictureReason(pic({ field_fulls: 1 }))).toBe(plain);
    expect(bestPictureReason(pic({ field_fulls: null }))).toBe(plain);
    // A scale below one would *inflate* the depth, so it is clamped, not honoured.
    expect(bestPictureReason(pic({ field_fulls: 0.25 }))).toBe(plain);
    expect(bestPictureReason(pic({ field_fulls: NaN }))).toBe(plain);
  });

  it("says nothing at all when the run carries neither total", () => {
    expect(
      bestPictureClauses(pic({ total_exposure_s: null, n_frames_used: 0, field_fulls: 4 })),
    ).toEqual([]);
  });
});

describe("isPinnedPick / pinnedNote", () => {
  it("treats an unpinned picture as auto-ranked and says nothing about it", () => {
    expect(isPinnedPick(pic({}))).toBe(false);
    expect(pinnedNote(pic({}))).toBeNull();
  });

  it("tolerates an older backend that never sends the field", () => {
    const { pinned: _drop, ...older } = pic({ pinned: false });
    expect(isPinnedPick(older as BestPicture)).toBe(false);
    expect(pinnedNote(older as BestPicture)).toBeNull();
  });

  it("explains a pinned favourite by name, and how to undo it", () => {
    const note = pinnedNote(pic({ pinned: true, target_name: "M42" }));
    expect(isPinnedPick(pic({ pinned: true }))).toBe(true);
    expect(note).toContain("M42");
    expect(note).toContain("cover");
    expect(note).toMatch(/History/);
  });
});
