import { MantineProvider } from "@mantine/core";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ImageLightbox } from "./ImageLightbox";

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
