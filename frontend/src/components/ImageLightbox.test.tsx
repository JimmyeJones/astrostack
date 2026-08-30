import { MantineProvider } from "@mantine/core";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImageLightbox, computePinch } from "./ImageLightbox";
import { ScanToPhoneButton } from "./ScanToPhoneButton";
import { FULL_RES_PNG_MAX_LONG_EDGE } from "../fullres";

function renderLightbox(props: Partial<React.ComponentProps<typeof ImageLightbox>> = {}) {
  return render(
    <MantineProvider>
      <ImageLightbox src="/img.png" title="M42" onClose={() => {}} {...props} />
    </MantineProvider>,
  );
}

function surfaceFor(): HTMLElement {
  const surface = screen.getByAltText("M42").parentElement;
  if (!surface) throw new Error("surface not found");
  // jsdom doesn't implement pointer capture.
  surface.setPointerCapture = () => {};
  return surface;
}

function wheel(el: HTMLElement, deltaY: number) {
  act(() => {
    el.dispatchEvent(new WheelEvent("wheel", { deltaY, bubbles: true, cancelable: true }));
  });
}

afterEach(() => vi.restoreAllMocks());

describe("ImageLightbox", () => {
  it("renders the image and starts at 100%", () => {
    renderLightbox();
    expect(screen.getByAltText("M42")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("zooms in on scroll up (wheel listener is actually bound)", () => {
    renderLightbox();
    wheel(surfaceFor(), -100);
    expect(screen.getByText("120%")).toBeInTheDocument();
  });

  it("zooms back out and clamps at 100%", () => {
    renderLightbox();
    const s = surfaceFor();
    wheel(s, -100);                 // 120%
    wheel(s, 100);                  // back toward 100%
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("offers no download when neither href is given", () => {
    renderLightbox();
    expect(screen.queryByLabelText("Download picture")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Download raw data")).not.toBeInTheDocument();
  });

  it("downloads the picture (PNG) being shown, not a scientific file", () => {
    renderLightbox({ downloadHref: "/api/run/1/preview" });
    const pic = screen.getByLabelText("Download picture");
    expect(pic).toHaveAttribute("href", "/api/run/1/preview");
    // No raw-data download unless one is explicitly provided.
    expect(screen.queryByLabelText("Download raw data")).not.toBeInTheDocument();
  });

  it("offers a PNG-or-JPEG menu when a jpeg href is also given", async () => {
    renderLightbox({ downloadHref: "/api/run/1/preview", jpegHref: "/api/run/1/jpeg" });
    // The picture control is now a menu trigger (button), not a bare anchor.
    const trigger = screen.getByLabelText("Download picture");
    expect(trigger).not.toHaveAttribute("href");
    fireEvent.click(trigger);
    const png = await screen.findByText("PNG (best quality)");
    const jpeg = screen.getByText("JPEG (smaller — best for sharing)");
    expect(png.closest("a")).toHaveAttribute("href", "/api/run/1/preview");
    expect(jpeg.closest("a")).toHaveAttribute("href", "/api/run/1/jpeg");
  });

  it("leads the download menu with the full-resolution PNG when one is given", async () => {
    renderLightbox({
      downloadHref: "/api/run/1/preview",
      fullResHref: "/api/run/1/full-res-png",
      jpegHref: "/api/run/1/jpeg",
    });
    const trigger = screen.getByLabelText("Download picture");
    fireEvent.click(trigger);
    const full = await screen.findByText("Full-res PNG (native size)");
    expect(full.closest("a")).toHaveAttribute("href", "/api/run/1/full-res-png");
    // The small preview is now honestly labelled, not "best quality".
    const preview = screen.getByText("Quick preview PNG (up to 1024px)");
    expect(preview.closest("a")).toHaveAttribute("href", "/api/run/1/preview");
    expect(screen.getByText("JPEG (smaller — best for sharing)").closest("a"))
      .toHaveAttribute("href", "/api/run/1/jpeg");
  });

  it("stops calling the full-res PNG native size on a canvas the render caps", async () => {
    // The endpoint decimates anything past its long-edge ceiling, so on a big
    // union mosaic "native size" was a promise the file didn't keep. Given the
    // canvas, the item says what it will actually hand over.
    renderLightbox({
      downloadHref: "/api/run/1/preview",
      fullResHref: "/api/run/1/full-res-png",
      fullResCanvas: { w: FULL_RES_PNG_MAX_LONG_EDGE + 2000, h: 6000 },
    });
    fireEvent.click(screen.getByLabelText("Download picture"));
    expect((await screen.findByText(
      `Full-res PNG (up to ${FULL_RES_PNG_MAX_LONG_EDGE} px)`)).closest("a"))
      .toHaveAttribute("href", "/api/run/1/full-res-png");
    expect(screen.queryByText("Full-res PNG (native size)")).not.toBeInTheDocument();
  });

  it("keeps the plain wording for an ordinary canvas, and when it isn't known", async () => {
    renderLightbox({
      downloadHref: "/api/run/1/preview",
      fullResHref: "/api/run/1/full-res-png",
      fullResCanvas: { w: 1080, h: 1920 },
    });
    fireEvent.click(screen.getByLabelText("Download picture"));
    expect(await screen.findByText("Full-res PNG (native size)")).toBeInTheDocument();
  });

  it("shows a full-res menu even without a jpeg href", async () => {
    renderLightbox({
      downloadHref: "/api/run/1/preview",
      fullResHref: "/api/run/1/full-res-png",
    });
    const trigger = screen.getByLabelText("Download picture");
    expect(trigger).not.toHaveAttribute("href");  // it's a menu, not a bare anchor
    fireEvent.click(trigger);
    expect((await screen.findByText("Full-res PNG (native size)")).closest("a"))
      .toHaveAttribute("href", "/api/run/1/full-res-png");
  });

  it("shows a Share icon when the browser can share files and share captions are given", () => {
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => true;
    nav.share = async () => {};
    renderLightbox({ jpegHref: "/api/run/1/jpeg", shareFilename: "m42.jpg", shareTitle: "M42" });
    expect(screen.getByLabelText("Share picture")).toBeInTheDocument();
    delete nav.canShare;
    delete nav.share;
  });

  it("shares the PNG when the surface has no JPEG", async () => {
    // Fail-before: the sheet was gated on `jpegHref`, so a Moon/Sun still — which
    // has only a display PNG — got no Share control, and on a phone (where the
    // QR is redundant with the OS's own sheet) that was the only control that
    // would have helped. The sheet hands the OS whatever the URL serves.
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => true;
    const shared: ShareData[] = [];
    nav.share = async (d: ShareData) => { shared.push(d); };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Blob(["x"], { type: "image/png" })),
    );
    renderLightbox({
      downloadHref: "/api/videos/Lunar_video/preview.png", shareFilename: "moon.png",
    });
    fireEvent.click(screen.getByLabelText("Share picture"));
    await waitFor(() => expect(shared).toHaveLength(1));
    expect(fetchSpy).toHaveBeenCalledWith("/api/videos/Lunar_video/preview.png");
    expect((shared[0].files as File[])[0].name).toBe("moon.png");
    delete nav.canShare;
    delete nav.share;
  });

  it("still prefers the JPEG for the share sheet when there is one", async () => {
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => true;
    nav.share = async () => {};
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Blob(["x"], { type: "image/jpeg" })),
    );
    renderLightbox({
      downloadHref: "/api/run/1/preview", jpegHref: "/api/run/1/jpeg",
      shareFilename: "m42.jpg",
    });
    fireEvent.click(screen.getByLabelText("Share picture"));
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith("/api/run/1/jpeg"));
    delete nav.canShare;
    delete nav.share;
  });

  it("omits the Share icon on a browser that can't share files", () => {
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => false;
    nav.share = async () => {};
    renderLightbox({ jpegHref: "/api/run/1/jpeg", shareFilename: "m42.jpg" });
    expect(screen.queryByLabelText("Share picture")).not.toBeInTheDocument();
    delete nav.canShare;
    delete nav.share;
  });

  it("offers the raw FITS as a distinct secondary download", () => {
    renderLightbox({ downloadHref: "/api/run/1/preview", rawHref: "/api/run/1/fits" });
    expect(screen.getByLabelText("Download picture")).toHaveAttribute("href", "/api/run/1/preview");
    expect(screen.getByLabelText("Download raw data")).toHaveAttribute("href", "/api/run/1/fits");
  });

  it("offers the phone QR from the PNG when the surface has no JPEG", () => {
    // Fail-before: the QR was gated on `jpegHref`, so a Moon/Sun still — which
    // has only a display PNG — got no way onto the phone at all, even though
    // the QR encodes nothing but a URL.
    renderLightbox({ downloadHref: "/api/videos/v/preview.png" });
    expect(
      screen.getByRole("button", { name: "Scan to get this picture on your phone" }),
    ).toBeInTheDocument();
  });

  it("prefers the JPEG for the phone QR when there is one", async () => {
    // The small share-friendly file is the better thing to pull over the LAN.
    // The QR renders as a path, not text, so compare it against the code the
    // JPEG URL produces on its own — and against the PNG's, which must differ.
    const openQrPath = async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Scan to get this picture on your phone" }),
      );
      const svg = await screen.findByRole("img", { name: /QR code/i });
      return svg.querySelector("path")?.getAttribute("d");
    };
    const forUrl = async (url: string) => {
      const { unmount } = render(
        <MantineProvider><ScanToPhoneButton url={url} /></MantineProvider>);
      const d = await openQrPath();
      unmount();
      return d;
    };
    const jpegCode = await forUrl("/api/run/1/jpeg");
    expect(jpegCode).not.toEqual(await forUrl("/api/run/1/preview"));

    renderLightbox({ downloadHref: "/api/run/1/preview", jpegHref: "/api/run/1/jpeg" });
    expect(await openQrPath()).toEqual(jpegCode);
  });

  it("offers no phone QR when there is no picture to point at", () => {
    renderLightbox({});
    expect(
      screen.queryByRole("button", { name: "Scan to get this picture on your phone" }),
    ).not.toBeInTheDocument();
  });

  it("names the secondary download whatever the surface calls it", () => {
    // A Moon/Sun still's heavier file is a 16-bit TIFF, not a FITS — calling it
    // "raw data (FITS)" there would be plainly wrong.
    renderLightbox({ rawHref: "/api/videos/v/download.tiff", rawLabel: "16-bit TIFF" });
    expect(screen.getByLabelText("Download 16-bit TIFF"))
      .toHaveAttribute("href", "/api/videos/v/download.tiff");
    expect(screen.queryByLabelText("Download raw data")).not.toBeInTheDocument();
  });

  it("renders a toolbarExtra control in the toolbar when given", () => {
    renderLightbox({ toolbarExtra: <button type="button">Wallpaper</button> });
    expect(screen.getByRole("button", { name: "Wallpaper" })).toBeInTheDocument();
  });

  it("does not crash on a pointermove that arrives after pointerup", () => {
    // Regression: the pan updater used to read drag.current inside setState,
    // which could run after pointerup had nulled it → crash.
    renderLightbox();
    const s = surfaceFor();
    wheel(s, -100); // zoom in so panning is enabled
    fireEvent.pointerDown(s, { clientX: 10, clientY: 10, pointerId: 1 });
    fireEvent.pointerMove(s, { clientX: 40, clientY: 30, pointerId: 1 });
    fireEvent.pointerUp(s, { pointerId: 1 });
    expect(() =>
      fireEvent.pointerMove(s, { clientX: 80, clientY: 60, pointerId: 1 }),
    ).not.toThrow();
  });
});

describe("ImageLightbox — the \"what stacking removed\" tint", () => {
  it("lays no overlay over the picture unless one is given", () => {
    renderLightbox();
    expect(screen.queryByTestId("lightbox-overlay")).not.toBeInTheDocument();
  });

  it("lays the tint over the picture, decoratively and without eating a drag", () => {
    renderLightbox({ overlaySrc: "/api/run/1/rejection-overlay" });
    const overlay = screen.getByTestId("lightbox-overlay");
    expect(overlay).toHaveAttribute("src", "/api/run/1/rejection-overlay");
    // Decorative: the caption is what a screen reader should hear, and the
    // tint must never swallow the pointer gestures the viewer runs on.
    expect(overlay).toHaveAttribute("aria-hidden");
    expect(overlay).toHaveAttribute("alt", "");
    expect(overlay.style.pointerEvents).toBe("none");
  });

  it("fits and moves the tint exactly like the picture, at every zoom level", () => {
    renderLightbox({ overlaySrc: "/api/run/1/rejection-overlay" });
    const pic = screen.getByAltText("M42");
    const overlay = screen.getByTestId("lightbox-overlay");
    const same = (el: HTMLElement) =>
      [el.style.maxWidth, el.style.maxHeight, el.style.objectFit,
       el.style.transform, el.style.transformOrigin].join("|");
    expect(same(overlay)).toBe(same(pic));
    // …and after a zoom, which is the case a separately-computed transform
    // would silently get wrong.
    wheel(surfaceFor(), -100);
    expect(same(overlay)).toBe(same(pic));
    expect(overlay.style.transform).toContain("scale(1.2)");
  });

  it("names what the marks are — a coloured speckle with no caption reads as damage", () => {
    renderLightbox({
      overlaySrc: "/api/run/1/rejection-overlay",
      overlayNote: "The cyan marks are what stacking removed.",
    });
    expect(screen.getByText("The cyan marks are what stacking removed."))
      .toBeInTheDocument();
  });

  it("says nothing about marks that aren't being shown", () => {
    renderLightbox({ overlayNote: "The cyan marks are what stacking removed." });
    expect(screen.queryByText("The cyan marks are what stacking removed."))
      .not.toBeInTheDocument();
  });
});

describe("computePinch", () => {
  it("scales by the finger-distance ratio (spread 100→200px = 2×)", () => {
    const r = computePinch(1, 100, 200, 200, 0, 150, 0);
    expect(r.scale).toBe(2);
    // The fixed image point (150) stays under the new midpoint (200): 200-150*2.
    expect(r.tx).toBe(-100);
  });

  it("pinching in shrinks and snaps back to fit at 1×", () => {
    const r = computePinch(2, 200, 50, 30, 30, 10, 10);
    expect(r.scale).toBe(1);     // clamped to MIN
    expect(r).toMatchObject({ tx: 0, ty: 0 });
  });

  it("clamps very large spreads to the max zoom", () => {
    expect(computePinch(2, 10, 100000, 0, 0, 0, 0).scale).toBe(12);
  });
});
