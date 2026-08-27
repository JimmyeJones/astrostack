import { describe, expect, it } from "vitest";
import type { BestPicture, VideoStill } from "./api/client";
import { formatStampDate } from "./format";
import {
  buildSlides, deepSkyFact, deepSkyMeta, nextIndex,
} from "./showAndTell";

function pic(over: Partial<BestPicture>): BestPicture {
  return {
    safe: "m31", target_name: "M31", run_id: 1, output_basename: "master",
    timestamp_utc: "2026-05-02T00:00:00Z", n_frames_used: 500,
    canvas_w: 480, canvas_h: 320, total_exposure_s: 12240, noise_sigma: 0.02,
    has_preview: true, has_fits: false, has_tiff: false,
    preview_url: "/api/targets/m31/stack-runs/1/preview", score: 1, ...over,
  };
}

function still(over: Partial<VideoStill>): VideoStill {
  return {
    capture_id: "cap1", label: "Moon", kind: "lunar",
    created_utc: "2026-05-03T00:00:00Z", width: 800, height: 600,
    n_stacked: 400, source_name: "moon.avi",
    preview_url: "/api/videos/cap1/preview", ...over,
  };
}

describe("deepSkyFact", () => {
  it("prefers the catalog's own one-liner", () => {
    expect(deepSkyFact(pic({ blurb: "The nearest big galaxy to our own." })))
      .toBe("The nearest big galaxy to our own.");
  });

  it("falls back to a plain sentence about the type, with the right article", () => {
    expect(deepSkyFact(pic({ object_type: "galaxy" }))).toBe("A galaxy.");
    expect(deepSkyFact(pic({ object_type: "open cluster" }))).toBe("An open cluster.");
  });

  it("says nothing at all when the catalog doesn't know the target", () => {
    // Also the shape an older backend sends (neither field present) — the
    // caption then just names the picture rather than padding with filler.
    expect(deepSkyFact(pic({}))).toBe("");
    expect(deepSkyFact(pic({ blurb: "   ", object_type: "" }))).toBe("");
  });
});

describe("deepSkyMeta", () => {
  it("reads date · integration · frames", () => {
    expect(deepSkyMeta(pic({ total_exposure_s: 12240, n_frames_used: 500 })))
      .toContain("3.4 h · 500 frames");
  });

  it("drops a clause an old run never recorded rather than printing a blank", () => {
    expect(deepSkyMeta(pic({ total_exposure_s: null, n_frames_used: 0 })))
      .toBe(formatStampDate("2026-05-02T00:00:00Z"));
    expect(deepSkyMeta(pic({ timestamp_utc: "", total_exposure_s: null, n_frames_used: 1 })))
      .toBe("1 frame");
  });
});

describe("buildSlides", () => {
  it("runs the ranked wall first, then the Moon/Sun stills", () => {
    const slides = buildSlides(
      [pic({ safe: "m31", target_name: "M31", run_id: 1 }),
       pic({ safe: "m42", target_name: "M42", run_id: 2 })],
      [still({ capture_id: "c1", label: "Moon", kind: "lunar" })],
    );
    expect(slides.map((s) => s.title)).toEqual(["M31", "M42", "Moon"]);
    // A deep-sky slide can be opened for more; a video still has no target page.
    expect(slides[0].href).toBe("/targets/m31/history");
    expect(slides[2].href).toBeUndefined();
  });

  it("captions the Moon and the Sun, which have no catalog entry of their own", () => {
    const [moon, sun, other] = buildSlides([], [
      still({ capture_id: "c1", kind: "lunar" }),
      still({ capture_id: "c2", kind: "solar", label: "Sun" }),
      still({ capture_id: "c3", kind: "other", label: "Clip" }),
    ]);
    expect(moon.fact).toMatch(/Moon/);
    expect(sun.fact).toMatch(/star/);
    expect(other.fact).toBe("");            // nothing true to say → say nothing
    expect(moon.meta).toBe(
      `${formatStampDate("2026-05-03T00:00:00Z")} · 400 frames stacked`);
  });

  it("skips a picture with no preview instead of showing a broken frame", () => {
    const slides = buildSlides(
      [pic({ preview_url: "" }), pic({ safe: "m42", run_id: 2 })],
      [still({ preview_url: "" })],
    );
    expect(slides).toHaveLength(1);
  });

  it("handles a library with nothing in it, and an older backend's missing videos", () => {
    expect(buildSlides(undefined, undefined)).toEqual([]);
    expect(buildSlides([], undefined)).toEqual([]);
  });
});

describe("nextIndex", () => {
  it("loops forwards and backwards", () => {
    expect(nextIndex(0, 3, 1)).toBe(1);
    expect(nextIndex(2, 3, 1)).toBe(0);
    expect(nextIndex(0, 3, -1)).toBe(2);
  });

  it("rests on a one-picture show rather than flickering", () => {
    expect(nextIndex(0, 1, 1)).toBe(0);
    expect(nextIndex(0, 0, 1)).toBe(0);
  });
});
