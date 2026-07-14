import { MantineProvider } from "@mantine/core";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ImageLightbox, computePinch } from "./ImageLightbox";

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

  it("offers the raw FITS as a distinct secondary download", () => {
    renderLightbox({ downloadHref: "/api/run/1/preview", rawHref: "/api/run/1/fits" });
    expect(screen.getByLabelText("Download picture")).toHaveAttribute("href", "/api/run/1/preview");
    expect(screen.getByLabelText("Download raw data")).toHaveAttribute("href", "/api/run/1/fits");
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
