import { describe, expect, it } from "vitest";
import { videoPreviewSrc } from "./videoPreviewSrc";

describe("videoPreviewSrc", () => {
  const still = {
    preview_url: "/api/videos/Lunar_video/preview.png",
    created_utc: "2026-08-06T21:00:00+00:00",
    width: 1920,
    height: 1080,
  };

  it("keys the cache buster on the size as well as the timestamp", () => {
    // A crop rewrites the picture at the same URL with the same "made at" time,
    // so without the size the browser would keep showing the uncropped version.
    const before = videoPreviewSrc(still);
    const after = videoPreviewSrc({ ...still, width: 620, height: 620 });
    expect(before).not.toBe(after);
    expect(before.startsWith("/api/videos/Lunar_video/preview.png?t=")).toBe(true);
  });

  it("is stable for a picture that hasn't changed", () => {
    expect(videoPreviewSrc(still)).toBe(videoPreviewSrc({ ...still }));
  });

  it("falls back to the timestamp when no size is known", () => {
    const src = videoPreviewSrc({
      preview_url: "/api/videos/x/preview.png", created_utc: "2026-08-06T21:00:00+00:00",
    });
    expect(src).toBe(
      `/api/videos/x/preview.png?t=${encodeURIComponent("2026-08-06T21:00:00+00:00")}`,
    );
  });

  it("escapes the key so the URL stays valid", () => {
    expect(videoPreviewSrc(still)).not.toContain("+00:00");
  });
});
