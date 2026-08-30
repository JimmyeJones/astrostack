import { afterEach, describe, expect, it, vi } from "vitest";
import {
  canSharePictureFiles,
  sharePicture,
  keepsakeFilename,
  sharePictureText,
  shareClipText,
  shareStillText,
} from "./share";
import type { CaptureLabel } from "./format";

/** A capture date the type system accepts. `sharePictureText` takes a branded
 *  `CaptureLabel` so a processing stamp cannot reach it (see `format.ts`); these
 *  are formatting tests, so they mint one directly rather than round-tripping a
 *  window through `formatCaptureNights`. */
const shot = (s: string) => s as CaptureLabel;

/** Install a fake Web Share API on `navigator`; returns a cleanup fn. */
function stubShare(opts: {
  canShare?: (data?: ShareData) => boolean;
  share?: (data?: ShareData) => Promise<void>;
} = {}) {
  const nav = navigator as unknown as Record<string, unknown>;
  const had = { canShare: "canShare" in nav, share: "share" in nav };
  const prev = { canShare: nav.canShare, share: nav.share };
  nav.canShare = opts.canShare;
  nav.share = opts.share;
  return () => {
    if (had.canShare) nav.canShare = prev.canShare;
    else delete nav.canShare;
    if (had.share) nav.share = prev.share;
    else delete nav.share;
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("canSharePictureFiles", () => {
  it("is false when the browser has no share/canShare", () => {
    const restore = stubShare({ canShare: undefined, share: undefined });
    expect(canSharePictureFiles()).toBe(false);
    restore();
  });

  it("is false when canShare rejects files (text-only share support)", () => {
    const restore = stubShare({ share: async () => {}, canShare: () => false });
    expect(canSharePictureFiles()).toBe(false);
    restore();
  });

  it("is true when the browser can share image files", () => {
    const restore = stubShare({ share: async () => {}, canShare: () => true });
    expect(canSharePictureFiles()).toBe(true);
    restore();
  });

  it("is false (never throws) when canShare itself throws", () => {
    const restore = stubShare({
      share: async () => {},
      canShare: () => { throw new Error("boom"); },
    });
    expect(canSharePictureFiles()).toBe(false);
    restore();
  });
});

describe("sharePicture", () => {
  const okFetch = () =>
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      blob: async () => new Blob([new Uint8Array([1, 2, 3])], { type: "image/jpeg" }),
    })));

  it("returns 'unsupported' when navigator.share is absent", async () => {
    const restore = stubShare({ share: undefined, canShare: undefined });
    okFetch();
    expect(await sharePicture({ url: "/x.jpg", filename: "x.jpg" })).toBe("unsupported");
    restore();
  });

  it("fetches the picture, wraps it in a File, and shares it", async () => {
    const share = vi.fn(async (_d?: ShareData) => {});
    const restore = stubShare({ share, canShare: () => true });
    okFetch();
    const outcome = await sharePicture({
      url: "/api/run/1/jpeg", filename: "m31.jpg", title: "M31", text: "M31 tonight",
    });
    expect(outcome).toBe("shared");
    expect(share).toHaveBeenCalledTimes(1);
    const data = share.mock.calls[0][0] as ShareData;
    expect(data.title).toBe("M31");
    expect(data.text).toBe("M31 tonight");
    expect(data.files?.[0]).toBeInstanceOf(File);
    expect(data.files?.[0].name).toBe("m31.jpg");
    restore();
  });

  it("returns 'cancelled' (not an error) when the user dismisses the sheet", async () => {
    const abort = Object.assign(new Error("cancelled"), { name: "AbortError" });
    const restore = stubShare({ share: async () => { throw abort; }, canShare: () => true });
    okFetch();
    expect(await sharePicture({ url: "/x.jpg", filename: "x.jpg" })).toBe("cancelled");
    restore();
  });

  it("returns 'error' when the picture can't be fetched", async () => {
    const restore = stubShare({ share: async () => {}, canShare: () => true });
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, blob: async () => new Blob() })));
    expect(await sharePicture({ url: "/missing.jpg", filename: "x.jpg" })).toBe("error");
    restore();
  });

  it("returns 'error' when share() throws a non-abort error", async () => {
    const restore = stubShare({
      share: async () => { throw new Error("platform failure"); },
      canShare: () => true,
    });
    okFetch();
    expect(await sharePicture({ url: "/x.jpg", filename: "x.jpg" })).toBe("error");
    restore();
  });

  it("returns 'unsupported' when the concrete file can't be shared", async () => {
    const share = vi.fn(async (_d?: ShareData) => {});
    // The concrete file (e.g. too large for this OS) is rejected by canShare.
    const restore = stubShare({ share, canShare: () => false });
    okFetch();
    expect(await sharePicture({ url: "/x.jpg", filename: "x.jpg" })).toBe("unsupported");
    expect(share).not.toHaveBeenCalled();
    restore();
  });
});

describe("sharePictureText", () => {
  it("captions with the name and date", () => {
    const { title, text, filename } = sharePictureText("M 31", shot("1/15/2026"));
    expect(title).toBe("M 31 · 1/15/2026");
    expect(text).toBe("M 31 — captured 1/15/2026");
    expect(filename).toBe("m-31.jpg");
  });

  it("omits the date when none is given", () => {
    const { title, text, filename } = sharePictureText("NGC 7000", null);
    expect(title).toBe("NGC 7000");
    expect(text).toBe("NGC 7000");
    expect(filename).toBe("ngc-7000.jpg");
  });

  it("falls back to a sensible default for a blank name", () => {
    const { title, filename } = sharePictureText("", shot(""));
    expect(title).toBe("My astrophoto");
    expect(filename).toBe("my-astrophoto.jpg");
  });

  it("never produces a bare '.jpg' filename from punctuation-only names", () => {
    expect(sharePictureText("***", null).filename).toBe("astrophoto.jpg");
  });

  it("names the file for what is actually being shared", () => {
    // A Moon/Sun still has only a PNG — sharing it called `.jpg` would confuse
    // whatever app it lands in. The caption is unaffected by the extension.
    const { title, filename } = sharePictureText("Moon", shot("1/15/2026"), "png");
    expect(filename).toBe("moon.png");
    expect(title).toBe("Moon · 1/15/2026");
  });

  it("falls back to .jpg for an unusable extension", () => {
    expect(sharePictureText("Moon", null, "").filename).toBe("moon.jpg");
    expect(sharePictureText("Moon", null, "!!").filename).toBe("moon.jpg");
  });
});

describe("shareStillText", () => {
  it("labels the date it has instead of calling it a capture date", () => {
    // A Moon/Sun still knows only when the app *stacked* the clip. Sharing that
    // as "captured" was the same wrong claim the picture share was fixed for,
    // so the still keeps the fact and labels it.
    const { title, text, filename } = shareStillText("Moon", "30 Aug 2026");
    expect(title).toBe("Moon · Stacked 30 Aug 2026");
    expect(text).toBe("Moon — stacked 30 Aug 2026");
    expect(text).not.toContain("captured");
    expect(filename).toBe("moon.png");
  });

  it("says just the name when there is no date", () => {
    const { title, text } = shareStillText("Sun", null);
    expect(title).toBe("Sun");
    expect(text).toBe("Sun");
  });

  it("shares a still as a PNG unless told otherwise", () => {
    // A still's picture *is* its PNG; one arriving named `.jpg` confuses the app
    // it lands in.
    expect(shareStillText("Moon", null).filename).toBe("moon.png");
    expect(shareStillText("Moon", null, "jpg").filename).toBe("moon.jpg");
    expect(shareStillText("***", null).filename).toBe("astrophoto.png");
    expect(shareStillText("", null).title).toBe("My astrophoto");
  });
});

describe("shareClipText", () => {
  it("captions the clip and uses the reel's extension", () => {
    const { title, text, filename } = shareClipText("M 31", "webp");
    expect(title).toBe("M 31 coming together");
    expect(text).toBe("Watch M 31 build up from noise, stacked with AstroStack");
    expect(filename).toBe("m-31-progress.webp");
  });

  it("uses a .png extension for an APNG reel", () => {
    expect(shareClipText("NGC 7000", "png").filename).toBe("ngc-7000-progress.png");
  });

  it("defaults to .webp for a missing or unrecognised format", () => {
    expect(shareClipText("M31", null).filename).toBe("m31-progress.webp");
    expect(shareClipText("M31", "gif").filename).toBe("m31-progress.webp");
  });

  it("falls back to a sensible default for a blank name", () => {
    const { title, filename } = shareClipText("", "webp");
    expect(title).toBe("My astrophoto coming together");
    expect(filename).toBe("my-astrophoto-progress.webp");
  });
});

describe("keepsakeFilename", () => {
  it("marks the framed variant so it can't overwrite the plain picture", () => {
    expect(keepsakeFilename("m-31.jpg")).toBe("m-31-keepsake.jpg");
    expect(keepsakeFilename(sharePictureText("NGC 7000").filename))
      .toBe("ngc-7000-keepsake.jpg");
  });

  it("keeps whatever extension it was handed", () => {
    expect(keepsakeFilename("moon.png")).toBe("moon-keepsake.png");
  });

  it("copes with a name that has no usable extension", () => {
    expect(keepsakeFilename("astrophoto")).toBe("astrophoto-keepsake");
    // A leading dot is the whole name, not an extension to split on.
    expect(keepsakeFilename(".jpg")).toBe(".jpg-keepsake");
  });

  it("never returns an empty or extension-less filename for junk input", () => {
    expect(keepsakeFilename("")).toBe("astrophoto-keepsake.jpg");
    expect(keepsakeFilename("   ")).toBe("astrophoto-keepsake.jpg");
  });
});
