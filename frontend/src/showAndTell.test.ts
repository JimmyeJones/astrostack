import { describe, expect, it } from "vitest";
import type { BestPicture, VideoStill } from "./api/client";
import { formatStampDate } from "./format";
import {
  buildSlides, deepSkyFact, deepSkyMeta, nextIndex, runSlideKey, showFromHref,
  startIndexFor, videoSlideKey,
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
      .toBe(`Stacked ${formatStampDate("2026-05-02T00:00:00Z")}`);
    expect(deepSkyMeta(pic({ timestamp_utc: "", total_exposure_s: null, n_frames_used: 1 })))
      .toBe("1 frame");
  });

  it("names the night the subs were shot when the run recorded one", () => {
    // This line calls itself an acquisition line; the run's own stamp is when
    // the *stack* ran, which on a re-stack of old data is a different year.
    expect(deepSkyMeta(pic({
      timestamp_utc: "2026-05-02T00:00:00Z", total_exposure_s: null,
      n_frames_used: 0, capture_night_start: "2024-11-15",
      capture_night_end: "2024-11-18",
    }))).toBe("Shot 15–18 Nov 2024");
  });

  it("says how many nights it took, when the run recorded that too", () => {
    // The slideshow is where someone *shows* the picture to another person, so
    // "over 4 nights" is the fact most worth having there — and the date range
    // beside it cannot supply it.
    expect(deepSkyMeta(pic({
      total_exposure_s: null, n_frames_used: 0,
      capture_night_start: "2024-11-15", capture_night_end: "2024-11-18",
      capture_nights: 4,
    }))).toBe("Shot over 4 nights, 15–18 Nov 2024");
    // …and stays quiet on a run made before the count existed.
    expect(deepSkyMeta(pic({
      total_exposure_s: null, n_frames_used: 0,
      capture_night_start: "2024-11-15", capture_night_end: "2024-11-18",
    }))).not.toContain("nights");
  });

  it("says which date it is, so a bare stamp can't be read as the capture night", () => {
    expect(deepSkyMeta(pic({ total_exposure_s: null, n_frames_used: 0 })))
      .toMatch(/^Stacked /);
    expect(deepSkyMeta(pic({
      total_exposure_s: null, n_frames_used: 0,
      capture_night_start: "2024-11-15", capture_night_end: "2024-11-15",
    }))).toMatch(/^Shot /);
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
    // A still carries only the date it was *made* — the app never learns when
    // the clip was shot — so it says so rather than sitting bare beside the
    // deep-sky slides' "Shot …".
    expect(moon.meta).toBe(
      `Stacked ${formatStampDate("2026-05-03T00:00:00Z")} · 400 frames stacked`);
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

describe("start the show here", () => {
  it("mints the same keys buildSlides does", () => {
    const slides = buildSlides([pic({ safe: "m42", run_id: 7 })],
      [still({ capture_id: "cap9" })]);
    expect(slides[0].key).toBe(runSlideKey("m42", 7));
    expect(slides[1].key).toBe(videoSlideKey("cap9"));
  });

  it("encodes the key into the link, so an odd safe name can't break it", () => {
    expect(showFromHref(runSlideKey("m42", 7))).toBe("/show?from=run%3Am42%3A7");
    expect(showFromHref(videoSlideKey("cap 9&x")))
      .toBe("/show?from=video%3Acap%209%26x");
  });

  it("starts on the named picture", () => {
    const slides = buildSlides(
      [pic({ safe: "m31", run_id: 1 }), pic({ safe: "m42", run_id: 2 })], []);
    expect(startIndexFor(slides, runSlideKey("m42", 2))).toBe(1);
  });

  it("falls back to the top of the wall rather than nothing", () => {
    const slides = buildSlides([pic({ safe: "m31", run_id: 1 })], []);
    // No key at all (the plain /show link), a key whose picture is gone, and an
    // empty show all play from the beginning.
    expect(startIndexFor(slides, null)).toBe(0);
    expect(startIndexFor(slides, "")).toBe(0);
    expect(startIndexFor(slides, "run:gone:99")).toBe(0);
    expect(startIndexFor([], "run:m31:1")).toBe(0);
  });
});
