import { afterEach, describe, expect, it, vi } from "vitest";
import { canSharePictureFiles, sharePicture, sharePictureText } from "./share";

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
    const { title, text, filename } = sharePictureText("M 31", "1/15/2026");
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
    const { title, filename } = sharePictureText("", "");
    expect(title).toBe("My astrophoto");
    expect(filename).toBe("my-astrophoto.jpg");
  });

  it("never produces a bare '.jpg' filename from punctuation-only names", () => {
    expect(sharePictureText("***", null).filename).toBe("astrophoto.jpg");
  });
});
