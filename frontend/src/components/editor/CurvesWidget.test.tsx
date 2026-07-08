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
