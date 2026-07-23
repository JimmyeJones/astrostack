import { describe, expect, it } from "vitest";
import { bestPictureClauses, bestPictureReason } from "./bestPictures";
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
