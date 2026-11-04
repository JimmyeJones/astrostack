import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CurvesWidget } from "./CurvesWidget";
import type { Pt } from "./curveDrag";

/** Render the widget with a controlled point list and capture onChange calls. */
function setup(initial: Pt[], ghost?: Pt[]) {
  const onChange = vi.fn();
  render(<MantineProvider>
    <CurvesWidget points={initial} onChange={onChange} ghost={ghost} />
  </MantineProvider>);
  return { onChange };
}

describe("CurvesWidget keyboard access (a11y)", () => {
  it("exposes each point as a focusable slider", () => {
    setup([[0, 0], [0.5, 0.5], [1, 1]]);
    const handles = screen.getAllByRole("slider");
    expect(handles).toHaveLength(3);
    handles.forEach((h) => expect(h).toHaveAttribute("tabindex", "0"));
    expect(handles[1]).toHaveAttribute("aria-label", "Curve point 2 of 3");
    expect(handles[0].getAttribute("aria-label")).toContain("endpoint");
  });

  it("nudges an interior point up with ArrowUp", () => {
    const { onChange } = setup([[0, 0], [0.5, 0.5], [1, 1]]);
    fireEvent.keyDown(screen.getAllByRole("slider")[1], { key: "ArrowUp" });
    // A nudge is continuous shaping → coalesce=true so a burst is one undo step.
    expect(onChange).toHaveBeenCalledWith([[0, 0], [0.5, 0.52], [1, 1]], true);
  });

  it("uses a coarser step with Shift", () => {
    const { onChange } = setup([[0, 0], [0.5, 0.5], [1, 1]]);
    fireEvent.keyDown(screen.getAllByRole("slider")[1], { key: "ArrowRight", shiftKey: true });
    const moved = onChange.mock.calls[0][0] as Pt[];
    expect(moved[1][0]).toBeCloseTo(0.6, 6);
  });

  it("removes an interior point with Delete", () => {
    const { onChange } = setup([[0, 0], [0.5, 0.5], [1, 1]]);
    fireEvent.keyDown(screen.getAllByRole("slider")[1], { key: "Delete" });
    // Removing a point is a discrete structural edit → its own undo step.
    expect(onChange).toHaveBeenCalledWith([[0, 0], [1, 1]], false);
  });

  it("keeps an endpoint's x locked when nudged horizontally", () => {
    const { onChange } = setup([[0, 0], [1, 1]]);
    fireEvent.keyDown(screen.getAllByRole("slider")[0], { key: "ArrowRight" });
    // x stays 0; only y could change (ArrowRight adds to x, which is locked → no move).
    expect(onChange).toHaveBeenCalledWith([[0, 0], [1, 1]], true);
  });

  it("adds a point via the keyboard-accessible 'add point' button", () => {
    const { onChange } = setup([[0, 0], [1, 1]]);
    fireEvent.click(screen.getByRole("button", { name: /add point/i }));
    expect(onChange).toHaveBeenCalledWith([[0, 0], [0.5, 0.5], [1, 1]], false);
  });
});

describe("CurvesWidget undo coalescing (discrete vs continuous)", () => {
  it("flags a structural edit (reset) as non-coalescing so it starts a fresh undo step", () => {
    const { onChange } = setup([[0, 0], [0.5, 0.7], [1, 1]]);
    fireEvent.click(screen.getByRole("button", { name: /reset/i }));
    expect(onChange).toHaveBeenCalledWith([[0, 0], [1, 1]], false);
  });
});

describe("CurvesWidget auto-contrast ghost", () => {
  it("draws a read-only dashed ghost curve when given a ghost shape", () => {
    setup([[0, 0], [1, 1]], [[0, 0], [0.25, 0.2], [0.75, 0.82], [1, 1]]);
    const ghost = screen.getByLabelText("auto contrast preview curve");
    expect(ghost.tagName.toLowerCase()).toBe("polyline");
    expect(ghost).toHaveAttribute("stroke-dasharray");
    // The ghost is not a draggable handle — no extra sliders beyond the 2 endpoints.
    expect(screen.getAllByRole("slider")).toHaveLength(2);
  });

  it("draws no ghost when none is supplied", () => {
    setup([[0, 0], [1, 1]]);
    expect(screen.queryByLabelText("auto contrast preview curve")).toBeNull();
  });
});

describe("CurvesWidget double-click to add", () => {
  /** Lay the 220-unit viewBox out at 220 px so clientX/Y are viewBox units. */
  function svgOf() {
    const svg = document.querySelector("svg") as SVGSVGElement;
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 220, height: 220,
      right: 220, bottom: 220, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    return svg;
  }

  it("adds an interior point where the user double-clicks", () => {
    const { onChange } = setup([[0, 0], [1, 1]]);
    fireEvent.doubleClick(svgOf(), { clientX: 110, clientY: 110 });
    const [next, coalesce] = onChange.mock.calls[0];
    expect(coalesce).toBe(false);
    expect(next).toHaveLength(3);
    expect(next[1][0]).toBeCloseTo(0.5, 6);
  });

  it("does not turn a double-click on the right padding into a new endpoint", () => {
    const { onChange } = setup([[0, 0], [1, 1]]);
    // x=216 is in the 10-unit padding right of the plot → clamps to x=1.
    fireEvent.doubleClick(svgOf(), { clientX: 216, clientY: 120 });
    const next = onChange.mock.calls[0][0] as Pt[];
    expect(next[next.length - 1]).toEqual([1, 1]);
    expect(next[1][0]).toBeLessThan(1);
  });
});
